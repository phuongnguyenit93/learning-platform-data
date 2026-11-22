# Tùy chỉnh xử lý lỗi bằng advice phù hợp với Spring Data REST exporter

## 1. Mục tiêu và luồng xử lý

Spring Data REST xuất các Spring Data repository thành REST resource thông qua Spring MVC. Khi một request đi vào endpoint do exporter tạo, exception được chuyển qua cơ chế xử lý lỗi của Spring MVC (DispatcherServlet và HandlerExceptionResolver). @ExceptionHandler trong @ControllerAdvice là điểm mở rộng phù hợp để chuyển exception thành HTTP status và response body có cấu trúc.

Điểm cần chú ý là advice phải nhắm đúng controller đang xử lý request. Một @RestControllerAdvice không giới hạn phạm vi sẽ áp dụng cho nhiều controller trong ứng dụng, trong khi controller do Spring Data REST exporter quản lý có phạm vi và message converter riêng. Vì vậy, trước khi viết handler, hãy xác định request thuộc endpoint repository được exporter sinh ra hay thuộc custom controller của ứng dụng.

## 2. Chọn phạm vi advice đúng với exporter

Spring Data REST có RepositoryRestExceptionHandler trong package org.springframework.data.rest.webmvc. API của lớp này cho thấy nó được đánh dấu bằng:

\`\`\`java
@ControllerAdvice(basePackageClasses = RepositoryRestExceptionHandler.class)
\`\`\`

Đây là dấu mốc package mà exporter dùng để giới hạn advice cho các controller Spring Data REST. Có thể dùng cùng class làm package marker cho advice tùy chỉnh của ứng dụng.

| Loại endpoint | Controller | Phạm vi advice nên dùng |
|---|---|---|
| Repository resource do exporter sinh | Controller nội bộ của Spring Data REST | @ControllerAdvice(basePackageClasses = RepositoryRestExceptionHandler.class) |
| Custom endpoint gắn với resource/repository | @RepositoryRestController | assignableTypes = MyRepositoryRestController.class hoặc basePackageClasses = MyRepositoryRestController.class |
| Custom operation khác nằm dưới basePath | @BasePathAwareController | Marker class hoặc package của controller ứng dụng |
| Endpoint Spring MVC thông thường | @Controller / @RestController | Advice của package hoặc controller đó; chỉ dùng advice global khi thực sự muốn áp dụng toàn ứng dụng |

@RepositoryRestController giúp custom controller dùng cấu hình của Spring Data REST như API base path, message converters và exception handling. Một controller chỉ dùng @Controller hoặc @RestController nằm ngoài phạm vi xử lý của Spring Data REST. Nếu cần custom operation dưới basePath nhưng không gắn với một repository resource cụ thể, tài liệu Spring Data REST hướng dẫn dùng @BasePathAwareController.

**Lưu ý quan trọng về package marker:** RepositoryRestExceptionHandler.class trỏ tới package của controller exporter (org.springframework.data.rest.webmvc). Nó không tự động chọn các custom controller đặt trong package com.example... của ứng dụng. Với custom controller, hãy dùng chính class controller hoặc một marker class trong package ứng dụng.

## 3. Ví dụ: ánh xạ exception nghiệp vụ thành ProblemDetail

Ví dụ dưới đây dùng Spring Framework 6 trở lên (thường đi cùng Spring Boot 3 trở lên). ProblemDetail biểu diễn lỗi theo RFC 9457 và cho phép thêm field riêng như code.

Exception nghiệp vụ:

\`\`\`java
public class CatalogRuleViolationException extends RuntimeException {

    public CatalogRuleViolationException() {
        super("Catalog cannot be changed in its current state");
    }
}
\`\`\`

Advice dành cho repository endpoint do exporter quản lý:

\`\`\`java
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.data.rest.webmvc.RepositoryRestExceptionHandler;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

@ControllerAdvice(basePackageClasses = RepositoryRestExceptionHandler.class)
@Order(Ordered.HIGHEST_PRECEDENCE)
public class SpringDataRestExporterAdvice {

    @ExceptionHandler(CatalogRuleViolationException.class)
    public ResponseEntity<ProblemDetail> handleCatalogRuleViolation(
            CatalogRuleViolationException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Tài nguyên đang ở trạng thái không cho phép thao tác này."
        );
        problem.setTitle("Xung đột nghiệp vụ");
        problem.setProperty("code", "CATALOG_RULE_CONFLICT");

        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
\`\`\`

Advice trên chỉ xử lý CatalogRuleViolationException. Các exception khác vẫn có thể đi tiếp tới handler mặc định của Spring Data REST. ResponseEntity cho phép chỉ định status và body; khi body là ProblemDetail, Spring MVC hỗ trợ content type application/problem+json hoặc application/problem+xml theo content negotiation.

Không đưa trực tiếp exception.getMessage() hoặc stack trace vào response công khai. Hãy trả thông điệp ổn định, có thể dịch được và mã lỗi dành cho client; ghi exception đầy đủ ở server log cùng correlation/request ID nếu hệ thống có cơ chế này.

### Nếu ứng dụng chưa dùng Spring Framework 6

ProblemDetail không có trong Spring Framework 5.x. Với Spring Boot 2 / Spring Framework 5, hãy dùng DTO lỗi của ứng dụng làm response body, ví dụ ApiError(code, message), rồi trả bằng ResponseEntity<ApiError>. Giữ nguyên phạm vi @ControllerAdvice và cách ánh xạ exception; chỉ thay kiểu body.

## 4. Ném exception từ Spring Data REST event handler

Exporter phát các event trong vòng đời thao tác với entity, gồm BeforeCreateEvent, BeforeSaveEvent, BeforeDeleteEvent và các event tương ứng sau thao tác. Có thể dùng annotated handler để kiểm tra quy tắc nghiệp vụ trước khi repository lưu entity.

\`\`\`java
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler
public class CatalogRepositoryEvents {

    @HandleBeforeCreate
    public void validateBeforeCreate(Catalog catalog) {
        if ("blocked".equalsIgnoreCase(catalog.getName())) {
            throw new CatalogRuleViolationException();
        }
    }
}
\`\`\`

Spring Data REST xác định domain type từ kiểu tham số đầu tiên của method được đánh dấu. Bean cần được đăng ký trong application context; @Component giúp component scan phát hiện bean. Khi kiểm tra thao tác cập nhật, dùng @HandleBeforeSave; chọn event tương ứng với thời điểm nghiệp vụ cần kiểm tra. Các Spring application event mặc định chạy đồng bộ, vì vậy exception phát sinh trong handler đồng bộ của request có thể đi lên luồng xử lý request để advice ánh xạ.

Nên giữ event handler tập trung vào kiểm tra nghiệp vụ và ném exception có ý nghĩa. Việc chọn HTTP status, tiêu đề lỗi và JSON response thuộc lớp web advice.

## 5. Advice cho custom @RepositoryRestController

Custom controller nằm trong package của ứng dụng, vì vậy selector cần trỏ tới controller đó hoặc package chứa nó.

\`\`\`java
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.http.ResponseEntity;

@RepositoryRestController
public class CatalogCommandController {

    @PostMapping("/catalogs/{id}/publish")
    public ResponseEntity<Void> publish(@PathVariable Long id) {
        // Thực hiện nghiệp vụ publish...
        throw new CatalogRuleViolationException();
    }
}
\`\`\`

Advice chỉ áp dụng cho controller trên:

\`\`\`java
@ControllerAdvice(assignableTypes = CatalogCommandController.class)
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CatalogCommandAdvice {

    @ExceptionHandler(CatalogRuleViolationException.class)
    public ResponseEntity<ProblemDetail> handle(CatalogRuleViolationException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Không thể publish catalog ở trạng thái hiện tại."
        );
        problem.setTitle("Xung đột nghiệp vụ");
        problem.setProperty("code", "CATALOG_RULE_CONFLICT");

        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
\`\`\`

Nếu nhiều custom controller cùng cần một advice, có thể dùng basePackageClasses = CatalogCommandController.class để chọn package ứng dụng. Nếu controller không gắn với repository resource mà chỉ cần hoạt động dưới basePath, cân nhắc @BasePathAwareController. Khi dùng @RepositoryRestController, path thực tế là RepositoryRestConfiguration.getBasePath() cộng với mapping của method.

## 6. Thứ tự và độ cụ thể của exception mapping

Spring MVC sắp xếp các bean @ControllerAdvice theo Ordered, @Order hoặc @Priority. Với exception handling, advice đầu tiên có method phù hợp sẽ được chọn. Trong cùng một advice, mapping khớp exception gốc thường được ưu tiên hơn mapping chỉ khớp cause. Tuy nhiên, mapping cause ở advice có độ ưu tiên cao vẫn có thể thắng mapping exception gốc ở advice có độ ưu tiên thấp hơn.

Áp dụng các nguyên tắc sau:

- Khai báo handler cho exception cụ thể, chẳng hạn CatalogRuleViolationException, thay vì bắt mọi Exception.
- Chỉ đặt @Order(Ordered.HIGHEST_PRECEDENCE) khi cần advice tùy chỉnh được xét trước handler mặc định hoặc advice khác.
- Không tạo catch-all trả mọi lỗi thành 400 hoặc 404; lỗi ngoài dự kiến cần tiếp tục được xử lý theo cơ chế mặc định và thường trả 500.
- Nếu handler quyết định không xử lý một exception, có thể ném lại chính exception đó để chuyển tiếp sang resolver/advice tiếp theo.
- Không cần kế thừa RepositoryRestExceptionHandler chỉ để thêm một mapping. Tạo advice riêng với selector và exception mapping rõ ràng sẽ dễ kiểm soát hơn.

Gợi ý chọn status:

| Tình huống | HTTP status thường dùng |
|---|---:|
| JSON sai cú pháp hoặc dữ liệu đầu vào không hợp lệ | 400 Bad Request |
| Resource thực sự không tồn tại | 404 Not Found |
| Trạng thái hiện tại xung đột với thao tác, ví dụ cập nhật resource đã khóa | 409 Conflict |
| Nội dung hợp lệ về cú pháp nhưng không thỏa quy tắc nghiệp vụ | 422 Unprocessable Content |
| Lỗi không dự kiến, không thể phân loại an toàn | 500 Internal Server Error |

Chọn status theo hợp đồng API hiện có và giữ nhất quán giữa các endpoint.

## 7. Kiểm thử bằng MockMvc

Không chỉ gọi trực tiếp method của controller hoặc advice. Cách gọi trực tiếp không kiểm tra request mapping, message conversion, DispatcherServlet hay @ExceptionHandler. MockMvc chạy luồng xử lý Spring MVC qua DispatcherServlet mà không cần khởi động HTTP server, phù hợp để xác nhận advice thực sự bắt exception trên endpoint exporter.

Ví dụ tích hợp với repository resource /catalogs và event handler ở phần trên:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SpringDataRestExceptionAdviceTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void mapsBusinessRuleFailureFromExporter() throws Exception {
        mockMvc.perform(post("/catalogs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_PROBLEM_JSON)
                        .content("""
                                {"name":"blocked"}
                                """))
                .andExpect(status().isConflict())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.title").value("Xung đột nghiệp vụ"))
                .andExpect(jsonPath("$.code").value("CATALOG_RULE_CONFLICT"));
    }
}
\`\`\`

Điều chỉnh /catalogs, JSON và dữ liệu theo mapping repository thật của ứng dụng. Nếu đã cấu hình RepositoryRestConfiguration.setBasePath("/api"), request test phải dùng /api/catalogs. Test nên kiểm tra cả HTTP status, content type và các field công khai trong response. Bổ sung một test cho request hợp lệ và một test cho exception không thuộc mapping tùy chỉnh để xác nhận handler mặc định vẫn hoạt động.

Với Spring Boot, @SpringBootTest mặc định tạo mock web environment; kết hợp @AutoConfigureMockMvc để inject MockMvc. Chạy bằng lệnh build của dự án, ví dụ ./mvnw test hoặc ./gradlew test.

## 8. Xử lý các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra / xử lý |
|---|---|---|
| Advice không được gọi với repository endpoint | Selector không nhắm tới package controller của exporter | Dùng basePackageClasses = RepositoryRestExceptionHandler.class cho controller exporter; kiểm tra exception có thực sự được ném ra |
| Advice không được gọi với custom controller | Custom controller ở package ứng dụng, nhưng advice lại dùng marker của package nội bộ Spring Data REST | Dùng assignableTypes hoặc basePackageClasses trỏ tới custom controller |
| Advice bắt cả controller MVC không liên quan | @ControllerAdvice không có selector nên áp dụng global | Giới hạn bằng package, class hoặc annotation selector |
| Handler mặc định xử lý trước mapping tùy chỉnh | Advice tùy chỉnh có thứ tự thấp hơn hoặc exception mapping không khớp | Kiểm tra @Order, kiểu exception gốc/cause và method signature |
| Response là HTML hoặc không có body như mong đợi | Handler trả view name hoặc content negotiation không phù hợp | Trả ResponseEntity / ProblemDetail; gửi Accept: application/problem+json khi kiểm thử |
| Không bắt được một phản hồi 404 | Code có thể đã trả ResponseEntity.notFound() thay vì ném exception | @ExceptionHandler chỉ xử lý exception; xác định nơi tạo status 404 và kiểm thử đúng luồng |
| Test gọi method thành công nhưng request HTTP vẫn lỗi | Test không đi qua DispatcherServlet và exception resolver | Dùng MockMvc với application context thật |
| Response làm lộ SQL hoặc chi tiết nội bộ | Body dùng trực tiếp exception.getMessage() hoặc stack trace | Trả thông điệp ổn định, log chi tiết ở server và giữ mã lỗi dành cho client |
| ProblemDetail không compile | Dự án đang dùng Spring Framework 5.x | Dùng DTO lỗi riêng với ResponseEntity; không nâng riêng một module Spring ngoài dependency management của Spring Boot |

## 9. Checklist triển khai

1. Xác định endpoint là repository resource do exporter sinh hay custom controller.
2. Chọn selector khớp package/class thực tế của controller.
3. Tạo exception nghiệp vụ riêng và map bằng @ExceptionHandler cụ thể.
4. Chọn HTTP status và response schema ổn định; không trả stack trace hoặc thông tin nhạy cảm.
5. Chỉ điều chỉnh @Order khi có xung đột với advice khác hoặc handler mặc định.
6. Dùng MockMvc kiểm tra request thật qua exporter, status, content type, body và hành vi của exception không được map.

## Tài liệu chính thức

- [Spring Data REST – Overriding Spring Data REST Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST – RepositoryRestExceptionHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html)
- [Spring Data REST – Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework – ControllerAdvice API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html)
- [Spring Framework – Exception handling with @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Framework – Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework – MockMvc overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html)
- [Spring Boot – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
