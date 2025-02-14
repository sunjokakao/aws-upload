package com.aws_upload.controller

import com.aws_upload.service.UserService
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/users")
class UserController(private val userService: UserService) {

    @GetMapping("/{email}")
    fun getUser(@PathVariable email: String): String? {
        return userService.getUserByEmail(email)
    }
}