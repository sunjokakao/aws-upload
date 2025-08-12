package com.aws_upload.service

import org.springframework.stereotype.Service

@Service
class UserService() {
    fun getUserByEmail(email: String): String { // 반환 타입 명시
        return "User: $email (Version: 3.0 - Auto Deploy)" 
    }
}