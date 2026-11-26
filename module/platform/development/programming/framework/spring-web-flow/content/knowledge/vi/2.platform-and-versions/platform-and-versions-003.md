# Ma trận tương thích giữa Web Flow 2.x, 3.x và 4.x

**Spring Web Flow (SWF)** mở rộng Spring MVC để mô hình hóa các hành trình web nhiều bước bằng `state`, `event`, `transition` và `subflow`. Flow có thể giữ bản nháp qua nhiều màn hình, bind và validate form, quản lý `flowScope` hoặc `conversationScope` rồi tiếp tục sau request kế tiếp. Những khả năng này dựa trên Spring Framework, Java, Servlet và các thư viện giao diện, vì vậy **tương thích phiên bản là một ma trận nhiều chiều**, không phải việc chỉ chọn số version của một JAR.

Bài thuộc chương **Nền tảng và phiên bản** của module `SPRING_WEB_FLOW`. Mục tiêu là đọc được ma trận tương thích **Web Flow 2.x, 3.x, 4.x**, phân biệt yêu cầu được tài liệu chính thức xác nhận với tổ hợp tham khảo, và tự kiểm chứng hệ thống trước khi tích hợp Spring MVC, binding/validation, scope, session hay thực hiện nâng cấp.

> **Mốc tham chiếu: 25/11/2026.** Những ví dụ version dưới đây dựa trên tài liệu chính thức Web Flow 2.5.1.RELEASE, 3.0.2 và 4.0.2, cùng tài liệu Spring Framework/Boot tương ứng. Khi sử dụng ở thời điểm khác, cần xem lại release notes, mức hỗ trợ và security advisories.

## 1. Đọc ma trận như thế nào?

Một tổ hợp chỉ được xem là ứng viên hợp lý khi **đồng thời** thỏa các trục sau:

1. **JDK** dùng chạy ứng dụng và mức bytecode của thư viện.
2. **Spring Framework**, bao gồm `spring-core`, `spring-context` và `spring-webmvc`.
3. **Servlet API và container**: có đúng thế hệ Java EE (`javax.servlet`) hoặc Jakarta EE (`jakarta.servlet`) không, có đáp ứng mức Servlet tối thiểu không?
4. **Spring Web Flow**: dòng tương ứng với nền Spring và version đã có bản vá phù hợp.
5. **Spring Boot** nếu ứng dụng dùng Boot: starter, BOM, embedded server và phiên bản Spring Framework thực sự được resolve.
6. **Tích hợp tùy chọn**: JSF/Spring Faces, Bean Validation, Spring Security, template engine, EL parser và kho lưu session/execution.
7. **Hành vi runtime**: các event, transition, form binding, validation, subflow, timeout và khôi phục flow hoạt động chính xác.

Trong bảng sử dụng các nhãn:

| Nhãn | Cách hiểu |
| --- | --- |
| **Phù hợp nền tảng** | Ghép theo thế hệ mà tài liệu SWF/Framework mô tả; vẫn phải kiểm tra bản vá và dependency thực tế |
| **Legacy** | Tổ hợp lịch sử có thể cần duy trì, nhưng phải đánh giá vòng đời hỗ trợ và lỗ hổng |
| **Cần xác minh** | Không đủ thông tin để kết luận; cần xem release cụ thể và chạy integration test |
| **Lệch nền tảng** | Không đáp ứng baseline đã biết hoặc trộn namespace/API giữa các thế hệ |

**Không có nghĩa** “Phù hợp nền tảng” là mọi minor/patch của các thư viện đều đã được thử nghiệm chung. Baseline là điều kiện bắt đầu, còn **dependency resolution và kiểm thử thực tế** mới là cơ sở cho quyết định triển khai.

## 2. Ma trận nền tảng chính: SWF × Java × Spring × Servlet

| Trục | Web Flow **2.0–2.4** | Web Flow **2.5.x** | Web Flow **3.0.x** | Web Flow **4.0.x** |
| --- | --- | --- | --- | --- |
| Tình trạng | Các nhánh lịch sử; yêu cầu thay đổi theo bản 2.x | Nhánh nâng cấp thế hệ 2 lên Spring 5 | Nhánh tương ứng Spring 6/Jakarta | Nhánh tương ứng Spring 7/Jakarta EE 11 |
| Java | **Không có một baseline chung** cho mọi bản 2.0–2.4; bản 2.4 yêu cầu JDK 6 | **Java 8+** | **Java 17+** | **Java 17+** |
| Spring Framework | Tùy từng bản 2.x; cần tra reference của bản đang dùng | **Spring Framework 5.0+**, trên thực tế chọn dòng **5.x** | Tài liệu ghi **Spring Framework 6.0+**; phù hợp nhất với thế hệ **6.x** | **Spring Framework 7.0 baseline** |
| Servlet/EE | Java EE/`javax.*` trong các ứng dụng truyền thống; mức API thay đổi theo đời dự án | **Servlet 3.1+**, `javax.servlet.*` | **Jakarta EE 9+** của Spring 6, `jakarta.servlet.*`; Servlet **5.0+** ở baseline Jakarta EE 9 | **Servlet 6.1**, `jakarta.servlet.*`, nền Jakarta EE 11 |
| JSF nếu dùng Spring Faces | Phụ thuộc từng bản; SWF 2.4 yêu cầu **JSF 2.0+** | **JSF 2.2+** | **JSF 4.0+** | **JSF 4.1+** |
| Dòng Spring Boot thường ghép | Các phiên bản Boot lịch sử; phải tra theo dự án | **Boot 2.x / Spring 5** | **Boot 3.x / Spring 6** | **Boot 4.x / Spring 7** |
| Namespace Servlet | `javax.servlet` | `javax.servlet` | `jakarta.servlet` | `jakarta.servlet` |
| Bản cụ thể để tra tài liệu | Tra chính xác phiên bản trong `2.0–2.4` | `2.5.1.RELEASE` (reference legacy) | `3.0.2` | `4.0.2` |

**Cơ sở của bảng:** [SWF 2.5.1 Reference](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/), [SWF 3.0.2 Reference](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/), [SWF 4.0.2 Reference](https://docs.spring.io/spring-webflow/docs/4.0.2/reference/), [Spring Framework 6 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes), [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions).

### 2.1. Vì sao chia 2.x thành hai cột?

“Web Flow 2.x” trải dài qua nhiều thế hệ Spring. Không thể nói tất cả các bản **2.0–2.5 đều yêu cầu Java 8/Spring 5**. Tài liệu phiên bản 2.5 ghi nhận:

- **2.4** yêu cầu **JDK 6**, bổ sung cấu hình Java, cải thiện integration MVC/flash scope và yêu cầu tối thiểu JSF 2.0.
- **2.5** là bước nâng để chạy trên **Spring Framework 5**, đi với **Java 8, Servlet 3.1, JSF 2.2** làm mức tối thiểu.
- Kể từ **2.5**, module `spring-js` không còn là module độc lập theo cách cũ; một số class chuyển vào `spring-webflow`, trong khi `spring-js-resources` là tùy chọn cần khai báo rõ nếu dùng.

Với một ứng dụng chạy **2.2** hoặc **2.3**, hãy tìm chính reference/release notes của bản đó; việc lấy thông số của **2.5** áp ngược về tất cả 2.x có thể dẫn đến đánh giá sai yêu cầu Java, JSF hoặc các module phụ thuộc.

### 2.2. Điều “Spring Framework 6.0 or higher” trong tài liệu SWF 3.0 có nghĩa gì?

SWF 3.0.2 Reference ghi Java 17+ và Spring Framework 6.0+. Tuy nhiên khi lên Spring Framework 7, SWF **4.0** đã được phát hành với baseline Spring 7. Vì vậy:

- **Spring 6.x → SWF 3.0.x** là ghép đúng thế hệ.
- **Spring 7.x → SWF 4.0.x** là ghép đúng baseline tài liệu.
- **Spring 7.x + SWF 3.0.x** không nên tự đánh dấu đã tương thích chỉ vì đọc chữ “or higher”: phải kiểm thử API/transitive dependency và cân nhắc nâng SWF 4.

Tương tự, “Java 17+” **không** phải là lời bảo đảm tự động tương thích với mọi JDK mới. Chọn JDK đã được toàn bộ hệ sinh thái ứng dụng, server, build plugin và thư viện bên thứ ba kiểm thử.

## 3. Ma trận theo thế hệ Spring Boot

Web Flow là một thư viện tích hợp với Spring MVC; Spring Boot giúp cấu hình ứng dụng và quản lý tập dependency. **Không có một công thức “version Spring Boot = version Web Flow”**. Cần nhìn Spring Framework và Servlet mà Boot thực sự mang vào.

| Hệ sinh thái | Spring Framework thường dùng | Java nền | Servlet/namespace | SWF nên kiểm tra trước |
| --- | --- | --- | --- | --- |
| **Spring Boot 2.x** | Spring 5.x | Tùy minor; thường từ Java 8 | Java EE / `javax.servlet` | **2.5.x** (legacy) |
| **Spring Boot 3.x** | Spring 6.x | Java 17+ | Jakarta EE, Servlet 5.0+/6.0 tùy minor/container | **3.0.x** |
| **Spring Boot 4.x** | Spring 7.x | Java 17+ | Jakarta EE 11, Servlet 6.1+ | **4.0.x** |

**Chú ý:** Bảng này mô tả **tổ hợp điển hình**, không xác nhận Boot BOM quản lý version `org.springframework.webflow:spring-webflow` trong mọi bản Boot. Khi khai báo SWF phải kiểm tra rõ artifact này có trong dependency management hay phải pin version; đồng thời xem Spring Framework và Servlet cuối cùng được chọn trên classpath.

### 3.1. Nền Boot 2.x

Spring Boot 2.5.1, chẳng hạn, có Spring Framework 5.3 và hỗ trợ Servlet 3.1+ với nhiều container. Đây là kiểu nền phù hợp với SWF 2.5. **Tuy nhiên** nhánh legacy phải được đánh giá về vòng đời hỗ trợ và bản vá an ninh, không nên dùng y nguyên một mẫu Boot 2 cũ để tạo ứng dụng mới.

### 3.2. Nền Boot 3.x

Spring Boot 3 dùng Spring Framework 6 và Java 17+. Do đó:

- SWF **3.0.x** là lựa chọn theo cùng thế hệ.
- Servlet/validation/JSF chuyển sang `jakarta.*`.
- Tên và version cụ thể của servlet container còn phụ thuộc bản Boot; đừng khóa cứng “mọi Boot 3 đều Servlet 6.0”.

### 3.3. Nền Boot 4.x

Spring Boot 4 dựa trên Spring Framework 7 và Jakarta EE 11, với baseline **Servlet 6.1**. Do đó:

- SWF **4.0.x** là dòng được tài liệu 4.0 mô tả cho nền tảng này.
- Java 17 là mức tối thiểu; cần kiểm tra version Java và khả năng tương thích runtime thực tế.
- Ví dụ Gradle/Maven mới phải xem starter MVC và dependency manager của Boot 4, vì một số cấu trúc starter thay đổi so với Boot 3.

Tham khảo [Spring Boot 4.0 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html), [Spring Boot 4 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) và [Spring Boot 3.0.2 Reference](https://docs.spring.io/spring-boot/docs/3.0.2/reference/htmlsingle/).

## 4. Ma trận Java: JDK build, JDK runtime và bytecode

“Dự án đang cài Java 21” chưa đủ để kết luận chọn SWF nào; phải biết **Spring Framework chính**.

| Java runtime | SWF 2.5 + Spring 5 | SWF 3.0 + Spring 6 | SWF 4.0 + Spring 7 |
| --- | --- | --- | --- |
| Java 8 | Theo baseline legacy | **Lệch nền tảng**: cần 17+ | **Lệch nền tảng**: cần 17+ |
| Java 11 | Cần xem bản Spring 5 và thư viện cụ thể | **Lệch nền tảng**: cần 17+ | **Lệch nền tảng**: cần 17+ |
| Java 17 | Xem mức hỗ trợ của bản Spring 5 và dependency legacy | **Đủ điều kiện JDK** | **Đủ điều kiện JDK** |
| Java 21 | Cần xác minh hỗ trợ legacy | Đủ mức tối thiểu; kiểm thử trên JVM 21 | Đủ mức tối thiểu; kiểm thử trên JVM 21 |
| Java 25 | Cần xác minh mức hỗ trợ legacy | Đủ mức tối thiểu; đối chiếu Spring 6/Boot và JVM 25 | Đủ mức tối thiểu; đối chiếu Spring 7/Boot và JVM 25 |

Đây là **ma trận điều kiện về Java**, chưa phải chứng nhận runtime. Ví dụ:

- Một ứng dụng Spring 5 chạy trên Java 17 vẫn mang Servlet namespace **`javax.*`**; JDK không tự chuyển nó thành Jakarta.
- **JDK dùng biên dịch** có thể khác **JDK chạy server**. `UnsupportedClassVersionError` có thể xuất hiện nếu class được biên dịch cho Java mới hơn runtime.
- Java runtime đáp ứng baseline nhưng server chưa có Servlet 6.1 thì **vẫn không đáp ứng SWF 4.0**.
- Các library JSF, driver database, bytecode manipulation, Gradle plugin và Kotlin (nếu có) cũng phải hỗ trợ Java đang chọn.

~~~mermaid
flowchart LR
    A["JDK build / toolchain"] --> B["Bytecode của ứng dụng"]
    C["Bytecode của SWF + Spring"] --> D["JVM runtime"]
    B --> D
    D --> E["Servlet container đúng thế hệ"]
    E --> F["Spring MVC + FlowExecutor"]
~~~

Điểm cần kiểm tra là **hai chiều**: bytecode/JDK phù hợp, và server/framework/API cũng phù hợp.

## 5. Ma trận Servlet và namespace Java EE/Jakarta EE

Ranh giới quan trọng nhất khi nâng từ SWF 2.x lên 3.x là chuyển **`javax.servlet.*` sang `jakarta.servlet.*`**; khi lên 4.x, yêu cầu mức **Servlet 6.1**.

| Trục kỹ thuật | SWF 2.5 / Spring 5 | SWF 3 / Spring 6 | SWF 4 / Spring 7 |
| --- | --- | --- | --- |
| Nền EE | Java EE 7/8 kiểu `javax` | Jakarta EE 9/10 kiểu `jakarta` | Jakarta EE 11 baseline |
| Servlet API tham chiếu | 3.1+; hệ Spring 5.3 có thể dùng Servlet 4.0 | Servlet 5.0+ theo nền Spring 6/Jakarta EE 9; cũng có cấu hình Servlet 6.0 | Servlet 6.1 |
| Request | `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` |
| Filter | `javax.servlet.Filter` | `jakarta.servlet.Filter` | `jakarta.servlet.Filter` |
| HttpSession | `javax.servlet.http.HttpSession` | `jakarta.servlet.http.HttpSession` | `jakarta.servlet.http.HttpSession` |
| Validation API | Thường `javax.validation.*` | `jakarta.validation.*` | `jakarta.validation.*` theo mức EE 11 |
| Container điển hình | Tomcat 9 cho nhiều ứng dụng Spring 5 | Tomcat 10.x tương ứng phiên bản Servlet cần dùng | Tomcat 11 hoặc container khác đáp ứng Servlet 6.1 |

Không suy rằng **Tomcat 10 bất kỳ** đều đáp ứng yêu cầu **SWF 4.0**: cần tra chính xác phiên bản Servlet mà container cung cấp. Với Spring 7, **Servlet 6.1** mới là mốc quyết định.

Ví dụ khác biệt kiểu Java:

~~~java
// Legacy: Spring Framework 5 / Servlet API theo Java EE
import javax.servlet.http.HttpSession;

// Khi migrate sang Spring 6/7, trong source mới dùng:
// import jakarta.servlet.http.HttpSession;
~~~

Hai package khai báo **hai kiểu khác nhau**. Đổi import trong controller không đủ nếu JAR của filter, validator, JSF component hoặc custom integration vẫn chỉ tham chiếu `javax.*`. Lỗi thường xuất hiện dưới dạng `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError` hoặc bean không khởi tạo được.

## 6. Ma trận tích hợp JSF, view, EL và validation

Không phải dự án SWF nào cũng dùng JSF; nhiều hệ thống chỉ dùng Spring MVC + Thymeleaf/JSP. Vì vậy phải đánh giá **phụ thuộc tùy chọn** theo đúng tính năng.

| Thành phần | Web Flow 2.5 | Web Flow 3.0 | Web Flow 4.0 |
| --- | --- | --- | --- |
| MVC + `DispatcherServlet` | Có | Có | Có |
| XML flow `view-state` / `transition` | Có | Có | Có |
| Spring Faces / JSF (nếu chọn) | JSF 2.2+ | JSF 4.0+ | JSF 4.1+ |
| JSF namespace/API | `javax.faces.*` thế hệ Java EE | `jakarta.faces.*` | `jakarta.faces.*` |
| Bean Validation | Javax Validation theo Spring 5 stack | Jakarta Validation theo Spring 6 | Jakarta Validation theo Spring 7 |
| Type conversion / formatting | Dựa vào Spring MVC, kiểm tra custom converter cũ | Cần kiểm tra các converter sau migration Jakarta/Spring 6 | Cần kiểm tra converter và phiên bản API sau Spring 7 |
| Expression parser | Có tích hợp biểu thức Spring/Unified EL tùy cấu hình | Có; cần chú ý bản vá liên quan Unified EL | Có; cần chú ý bản vá liên quan Unified EL |
| View engine | JSP/Thymeleaf/JSF tùy cấu hình; có thể gặp Tiles ở legacy | Chọn implementation tương thích Jakarta | Chọn implementation tương thích Spring 7/Jakarta EE 11 |

**Các yếu tố không thay đổi mục tiêu:** state điều hướng vẫn biểu diễn hành trình, event vẫn kích hoạt transition, `flowScope` vẫn dành cho dữ liệu một flow execution. Tuy nhiên **chi tiết integration có thể đổi** do phiên bản framework, converter, expression parser, rendering và session repository.

### 6.1. Spring Faces là dependency riêng

Nếu dùng JSF với SWF, kiểm tra `spring-faces` và implementation JSF tương ứng. Không nên suy rằng chỉ thêm `spring-webflow` đã đủ chạy tất cả tính năng JSF. Theo reference:

- SWF 2.5: JSF **2.2+**.
- SWF 3.0: JSF **4.0+**.
- SWF 4.0: JSF **4.1+**.

JSF 4 dùng `jakarta.faces.*`. Khi migrate, cần kiểm tra custom tag library, component library, Facelets và `FacesServlet`. Đối với dự án chỉ dùng Spring MVC, không cần kéo JSF vào chỉ vì Web Flow có hỗ trợ JSF.

### 6.2. Form binding và validation phải được kiểm thử dù XML giữ nguyên

Ví dụ một phần view-state:

~~~xml
<view-state id="enterDetails" view="booking/details" model="booking">
    <binder>
        <binding property="guestName" required="true" />
        <binding property="checkInDate" required="true" />
    </binder>
    <transition on="next" to="review"/>
</view-state>
~~~

Đoạn XML minh họa **binding whitelist** cho form; chưa phải định nghĩa flow hoàn chỉnh. Khi đổi từ Spring 5 sang 6 hoặc 7, phải thử:

1. Tên property được phép bind; các field ngoài danh sách không bị sửa.
2. Converter ngày/giờ/số có còn hợp lệ theo cấu hình `ConversionService`/formatter.
3. Validator của model dùng namespace `javax.validation` hay `jakarta.validation` đúng thế hệ.
4. Event `next` chỉ chuyển sang review khi binding/validation và action đáp ứng chính sách.
5. Thông báo lỗi hiển thị đúng locale; dữ liệu bản nháp vẫn nằm ở scope được thiết kế.

Không dùng thành công của bước compile để kết luận **binding/validation đã tương thích**.

## 7. Ma trận tổ hợp thực tế: được, cần kiểm tra hay lệch nền

| # | Tổ hợp ứng dụng | Đánh giá | Lý do / hành động |
| --- | --- | --- | --- |
| 1 | Java 8 + Spring 5.3 + Servlet `javax` + SWF 2.5 | **Legacy** | Đúng thế hệ, nhưng phải kiểm tra hỗ trợ và bản vá SWF 2.5 |
| 2 | Java 17 + Boot 2.x/Spring 5.3 + SWF 2.5 | **Cần xác minh** | Java đủ cho SWF 2.5; vẫn cần mức hỗ trợ của minor Boot/Spring/container |
| 3 | Java 8 + Spring 6 + SWF 3.0 | **Lệch nền tảng** | Spring 6/SWF 3 đòi Java 17+ |
| 4 | Java 17 + Spring 6 + Servlet Jakarta + SWF 3.0.2 | **Phù hợp nền tảng** | Đúng nhánh Spring 6, cần dependency tree và test MVC/flow |
| 5 | Java 21 + Boot 3.x/Spring 6 + SWF 3.0.2 | **Cần xác minh** | Đủ Java tối thiểu, kiểm tra minor Spring/Boot hỗ trợ JDK 21 và các tích hợp |
| 6 | Java 17 + Spring 6 + `javax.servlet` + SWF 3 | **Lệch nền tảng** | Mismatch namespace, cần chuyển Servlet/integration sang Jakarta |
| 7 | Java 17 + Spring 7 + Servlet 6.1 + SWF 4.0.2 | **Phù hợp nền tảng** | Khớp baseline; kiểm tra patch và integration |
| 8 | Java 21 + Boot 4.x/Spring 7 + Servlet 6.1 + SWF 4.0.2 | **Phù hợp nền tảng** | Khớp thế hệ; vẫn kiểm tra dependency và test hành vi |
| 9 | Java 17 + Spring 7 + Servlet 5.0 + SWF 4 | **Lệch nền tảng** | SWF 4 yêu cầu Servlet 6.1 |
| 10 | Java 17 + Spring 6 + Servlet 6.0 + SWF 4 | **Lệch nền tảng** | SWF 4 có baseline Spring 7/Servlet 6.1 |
| 11 | Java 17 + Spring 7 + Servlet 6.1 + SWF 3 | **Cần xác minh** | SWF 3 có mô tả Spring 6.0+ nhưng SWF 4 mới là dòng theo Spring 7 |
| 12 | Java 17 + Spring 6 + SWF 2.5 (`javax`) | **Lệch nền tảng** | Trộn thư viện Java EE/Spring 5 với Spring 6/Jakarta |
| 13 | Java 17 + Spring 6 + SWF 3 + JSF 2.3 | **Lệch nền tảng** | Tích hợp Faces của SWF 3 yêu cầu JSF 4.0+ |
| 14 | Java 17 + Spring 7 + SWF 4 + JSF 4.0 | **Lệch nền tảng** | Tích hợp Faces của SWF 4 yêu cầu JSF 4.1+ |

**Lưu ý về nhãn:** “Cần xác minh” nghĩa là chưa có đủ chứng cứ để phê duyệt, **không** đồng nghĩa đã hỏng. “Phù hợp nền tảng” cũng không thay thế integration test.

### 7.1. Cách xử lý ba tình huống thường gây nhầm

**Tình huống A — nâng JDK nhưng giữ nguyên Spring.** Ứng dụng từ Java 8 lên 17, vẫn Spring 5/Servlet `javax`. Đây **không phải nâng sang SWF 3**; trục JDK đã đổi, các trục Framework/Servlet chưa đổi.

**Tình huống B — nâng Spring Boot 2 lên 3.** Boot 3 kéo Spring 6 và Jakarta. Nếu còn SWF 2.5 hoặc plugin/filter dùng `javax`, đó là điểm chặn; cần chuyển SWF 3 và integration phụ thuộc sang Jakarta.

**Tình huống C — nâng Boot 3 lên 4.** Boot 4 chuyển Spring 7 và Servlet 6.1. Cần đồng bộ SWF 4, kiểm tra container, starter, JSF nếu có; đừng chỉ nâng version BOM rồi giữ Web Flow 3 mà chưa đánh giá.

## 8. Ma trận bản vá và vòng đời hỗ trợ

Tương thích về API **không đồng nghĩa an toàn để triển khai**. Với một module có form binding và expression language, bản vá Web Flow đặc biệt quan trọng.

| Dòng | Phiên bản nguồn tham khảo | Tình hình bản vá liên quan | Hành động |
| --- | --- | --- | --- |
| 2.5.x | `2.5.1.RELEASE` là reference OSS thường gặp | CVE-2026-40985 ảnh hưởng bản `2.5.1.RELEASE` trở xuống; bản `2.5.2` theo advisory chỉ có qua hỗ trợ doanh nghiệp | Xem kênh hỗ trợ hợp lệ hoặc xây kế hoạch nâng cấp |
| 3.0.x | `3.0.2` | `3.0.0–3.0.1` bị ảnh hưởng; **3.0.2** là bản sửa OSS công bố 10/06/2026 | Chọn bản đã vá phù hợp dòng 3.0 |
| 4.0.x | `4.0.2` (19/11/2026) | `4.0.0` bị ảnh hưởng; **4.0.1** là bản sửa OSS, **4.0.2** là bản phát hành mới hơn | Chọn bản 4.0 đã vá; kiểm tra release note tiếp theo |

Theo thông báo của Spring ngày **10/06/2026**, **3.0.2** và **4.0.1** giải quyết:

- **CVE-2026-40985** — vấn đề data binding khi cấu hình Unified EL parser trong những điều kiện nhất định.
- **CVE-2026-40986** — cách JavaScript `RemotingHandler` render một response không phải HTML như HTML.

Advisory của CVE-2026-40985 mô tả điều kiện khai thác cụ thể, bao gồm cấu hình parser `WebFlowELExpressionParser`/`ELExpressionParser`, `useSpringBinding` không bật và không khai báo binding property tại view-state. **Không được suy rằng mọi ứng dụng cùng phiên bản đều có cùng điều kiện khai thác**, nhưng mọi dự án phải xem advisory để xác định ảnh hưởng.

Nguồn: [Spring Security Advisory CVE-2026-40985](https://spring.io/security/cve-2026-40985/), [Thông báo phát hành bảo mật SWF 3.0.2 / 4.0.1](https://spring.io/blog/2026/06/10/spring-webflow-4-0-1-and-3-0-2-available-now/), [Spring Web Flow Releases](https://github.com/spring-projects/spring-webflow/releases).

Không lấy `2.5.1.RELEASE` hay `3.0.0` từ một bài hướng dẫn cũ để làm mặc định production. Sau khi xác định dòng phù hợp, **chọn bản vá đang được hỗ trợ** và đối chiếu các advisory hiện hành của Spring, Servlet container, Security và JSF.

## 9. Ma trận artifact và dependency cần kiểm tra

| Artifact / thành phần | Vai trò | Cách đánh giá |
| --- | --- | --- |
| `org.springframework.webflow:spring-webflow` | Engine flow, state, transition, MVC integration | Version 2.x/3.x/4.x phải hợp với Spring/Servlet |
| `org.springframework.webflow:spring-faces` (khi dùng JSF) | Tích hợp JSF | Ghép đúng thế hệ SWF và version JSF |
| `org.springframework:spring-core` | Spring core abstractions | Đúng Spring Framework 5/6/7 tương ứng |
| `org.springframework:spring-context` | IoC, bean lifecycle | Đồng bộ với `spring-core` |
| `org.springframework:spring-webmvc` | `DispatcherServlet`, handler mapping/adapter, binding | Đồng bộ với Spring Framework chính |
| Servlet API | Request, response, filter, session | `javax` cho legacy 2.5; `jakarta` và đủ mức Servlet cho 3/4 |
| Bean Validation provider | Kiểm tra form/model | Dùng implementation đúng namespace |
| Spring Security nếu dùng | Authentication/authorization, CSRF | Cần version tương thích Spring thế hệ hiện tại |
| View engine/JSF | Render màn hình và fragment | Kiểm tra phiên bản, namespace và implementation |

### 9.1. Maven: kiểm tra version đã resolve

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.webflow,org.springframework
mvn help:effective-pom
~~~

Các lệnh trên cho phép thấy dependency trực tiếp, transitive và dependency management. `-Dincludes` giúp lọc nhanh hai group liên quan; nếu cần kiểm tra Servlet, Security, Jakarta/Javax API và JSF thì mở rộng bộ lọc hoặc xem toàn bộ tree.

### 9.2. Gradle: kiểm tra runtime classpath

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webflow
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webmvc
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jakarta.servlet-api
~~~

Các lệnh là **hướng dẫn thao tác tại dự án**, không phải kết quả đã chạy của bài học này. Đối với WAR có Servlet API ở scope `provided`, phải kiểm tra **server thực tế**, vì runtime classpath ở build local có thể không phản ánh đầy đủ thư viện mà application server cung cấp.

### 9.3. Nhận diện xung đột từ dependency tree

Các dấu hiệu cần xử lý:

~~~text
spring-webflow:2.5.1.RELEASE
spring-webmvc:6.x
jakarta.servlet-api:5.0+
# Trộn thế hệ javax (SWF 2.5) và Jakarta (Spring 6).

spring-webflow:4.0.2
spring-webmvc:7.x
javax.servlet-api:4.0
# Sai Servlet namespace/mức API cho Spring 7/SWF 4.
~~~

Các dòng trên là **ví dụ giả định về cấu hình sai**, không phải log do công cụ tạo ra. Khi chẩn đoán, kiểm tra **module được chọn ở classpath runtime**, các exclusion, version constraint, BOM và JAR do container cung cấp; tránh chỉ nhìn khai báo `implementation`.

## 10. Ma trận tác động khi nâng cấp tính năng Web Flow

Đổi dòng framework có thể giữ nguyên XML mà vẫn làm hành vi luồng khác đi. Cần phân tích mỗi tính năng theo chủ sở hữu:

| Chức năng | Điểm liên quan tới tương thích | Kiểm thử cần có |
| --- | --- | --- |
| Mở flow | Spring MVC `HandlerMapping`, `FlowHandlerAdapter`, URL và view | GET khởi tạo flow, truy cập đúng state đầu |
| Điều hướng state | Engine, event parsing, transition definition | `next`, `back`, `cancel` và event không hợp lệ |
| Binding form | MVC/SWF binder, converter, allowed properties | Trường hợp hợp lệ, thiếu field, field ngoài whitelist |
| Validation | Jakarta/Javax validation provider, Spring converter | Lỗi dừng transition và hiện đúng thông báo |
| Subflow | Mapping input/output, state result, conversation | Subflow trả event đúng và không mất dữ liệu |
| `flowScope` / `viewScope` | Flow execution lifecycle | Bản nháp được giữ/giải phóng đúng lúc |
| HTTP session | Servlet container, cookie, session store | Timeout, logout, nhiều tab, triển khai nhiều node |
| Xác thực/phân quyền | Spring Security + route/flow action | Truy cập trái phép và event gửi thủ công bị chặn |
| Render view/Ajax | ViewResolver, template engine, JSF, fragment | Full page và partial rendering đúng |
| Xử lý lỗi | Exception handler/listener, execution repository | Flow hết hạn, action lỗi, khởi tạo lại an toàn |

### 10.1. Một flow để kiểm tra ba thế hệ

~~~mermaid
stateDiagram-v2
    [*] --> details
    details --> review: next
    details --> cancelled: cancel
    review --> details: back
    review --> confirm: submit
    confirm --> done: success
    confirm --> review: error
    done --> [*]
    cancelled --> [*]
~~~

Có thể dùng mẫu XML đơn giản minh họa cùng logic:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="booking" class="com.example.booking.BookingDraft"/>

    <view-state id="details" view="booking/details" model="booking">
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="back" to="details"/>
        <transition on="submit" to="confirm"/>
    </view-state>

    <action-state id="confirm">
        <evaluate expression="bookingService.save(booking)"/>
        <transition on="success" to="done"/>
        <transition on="error" to="review"/>
    </action-state>

    <end-state id="done" view="booking/done"/>
    <end-state id="cancelled" view="booking/cancelled"/>
</flow>
~~~

Đây là **minh họa**: class `BookingDraft`, bean `bookingService`, view, converter, validator và cấu hình Web Flow MVC cần được tạo riêng. Kết quả event `success`/`error` của action phải được service/action trả đúng contract; lỗi nghiệp vụ không tự động trở thành event `error` nếu chưa được xử lý. Khi chạy trên một dòng SWF cụ thể, cần xác minh XML schema và hạ tầng thực tế.

Để đối chiếu 2.x/3.x/4.x, tạo **môi trường thử nghiệm độc lập cho từng dòng**, không trộn JAR của nhiều dòng vào cùng classpath. Sau đó so sánh:

1. Request khởi tạo flow có thành công?
2. Form có giữ và bind đúng dữ liệu `booking`?
3. Event `next`/`back` có chuyển đúng state?
4. Khi lỗi validation, view có giữ dữ liệu và thông báo?
5. Sau `submit`, service có được gọi đúng và thao tác ghi có idempotent?
6. Khi session timeout, execution key cũ được xử lý ra sao?
7. Người dùng mở hai tab/flow execution có bị trộn trạng thái?

Không thay đổi dữ liệu giao dịch dựa vào việc “flow có thể chạy tới cuối”. Việc xác nhận phải dùng các bất biến ở service/database.

## 11. Quy trình kiểm duyệt một tổ hợp chưa có trong bảng

~~~mermaid
flowchart TD
    A["Nhận 5 giá trị: JDK, Spring, Servlet, SWF, Boot/JSF"] --> B{"JDK đạt tối thiểu?"}
    B -->|"Không"| X["Lệch nền tảng: nâng runtime"]
    B -->|"Có"| C{"Spring/Servlet đúng baseline SWF?"}
    C -->|"Không"| Y["Lệch nền tảng: đồng bộ framework/container"]
    C -->|"Có"| D{"Namespace và tùy chọn JSF/validation đúng?"}
    D -->|"Không"| Z["Sửa hoặc nâng integration"]
    D -->|"Có"| E["Kiểm tra dependency tree + bản vá"]
    E --> F{"Resolve sạch và không còn bản dễ tổn thương?"}
    F -->|"Không"| G["Xử lý version conflict / security advisory"]
    F -->|"Có"| H["Chạy flow integration tests"]
    H --> I{"State, event, binding, session đạt?"}
    I -->|"Không"| J["Phân tích regression"]
    I -->|"Có"| K["Ứng viên có bằng chứng tương thích để triển khai"]
~~~

Cách triển khai:

1. **Ghi lại phiên bản thực tế**: `java -version`, file build, BOM, output dependency tree, version Servlet do container cung cấp.
2. **Xác định thế hệ nền tảng**: Spring 5/Java EE, Spring 6/Jakarta EE 9–10, hoặc Spring 7/Jakarta EE 11.
3. **Chọn dòng SWF**: 2.5 legacy, 3.0 cho Spring 6, 4.0 cho Spring 7; bản 2.0–2.4 phải tra riêng.
4. **Đối chiếu module tùy chọn**: Spring Faces, JSF, Bean Validation, Spring Security, view engine.
5. **Kiểm tra phiên bản vá**: advisory của SWF và toàn bộ hệ Spring.
6. **Thử flow tối thiểu rồi flow thực tế**: các transition, binding, session, subflow và kịch bản lỗi.
7. **Lưu kết quả**: chọn/không chọn dựa trên phiên bản đã resolve và test PASS; ghi blocker cụ thể nếu chưa đạt.

## 12. Bài tập ma trận có đáp án

### Bài tập 1 — phân biệt ba nguyên nhân không tương thích

Cho ba dự án:

| Dự án | Cấu hình | Kết luận ban đầu |
| --- | --- | --- |
| A | Java 11, Spring 6.0, SWF 3.0 | **Sai JDK**: cần Java 17+ |
| B | Java 17, Spring 6.2, SWF 2.5.1, Tomcat 10 | **Sai thế hệ SWF/namespace**: SWF 2.5 dùng `javax`, Spring 6 dùng `jakarta` |
| C | Java 17, Spring 7.0, SWF 4.0.2, Servlet 6.0 | **Sai Servlet baseline**: SWF 4 cần Servlet 6.1 |

Đừng chữa A bằng việc hạ riêng SWF xuống 2.5; việc này sẽ lại xung đột với Spring 6. Phải quyết định **cả tổ hợp nền tảng**.

### Bài tập 2 — phân loại theo các nhãn

Xét các tổ hợp:

1. Java 17 + Spring 6.2 + SWF 3.0.2 + Jakarta Servlet 6.0.
2. Java 21 + Spring 7.0 + SWF 4.0.2 + Servlet 6.1.
3. Java 17 + Spring 7.0 + SWF 3.0.2 + Servlet 6.1.
4. Java 8 + Spring 5.3 + SWF 2.5.1 + Servlet 4.0.

**Gợi ý đáp án:** (1) và (2) phù hợp nền tảng, vẫn cần test; (3) cần xác minh nhưng SWF 4 là nhánh đúng baseline Spring 7; (4) là tổ hợp legacy và phải đánh giá bản vá/hỗ trợ. Các nhãn không nói thay khả năng chạy thực tế.

### Bài tập 3 — phát hiện migration thiếu

Một ứng dụng có:

~~~text
JDK: 17
Spring Framework: 6.2.x
Spring Web Flow: 3.0.2
Servlet: Jakarta
JSF: 2.3 (javax.faces.*)
~~~

**Hỏi:** Spring MVC flow không dùng JSF có thể cần kiểm tra gì? Nếu flow dùng JSF thì nguyên nhân chặn là gì?

**Đáp án:** Với MVC-only, kiểm tra classpath để bảo đảm JSF 2.3 không bị kéo vào runtime hoặc ảnh hưởng bean/config không cần thiết; nếu dùng JSF, SWF 3.0 yêu cầu **JSF 4.0+** và integration theo `jakarta.faces.*`. Cần nâng cả implementation, library component, view và cấu hình `FacesServlet`.

### Bài tập 4 — đề xuất kế hoạch thử nghiệm

Cho hệ thống đang dùng Spring 5/SWF 2.5, có flow đặt hàng 4 bước, JSF 2.2 và session timeout 30 phút. Hãy lập bảng theo thứ tự kiểm thử để lên Spring 6/SWF 3:

| Thứ tự | Nhóm kiểm tra | Minh chứng tối thiểu |
| --- | --- | --- |
| 1 | Java/Spring/Servlet | Java 17, Spring 6, Jakarta API thống nhất |
| 2 | JSF | JSF 4.0+, Spring Faces và component library tương thích |
| 3 | Wiring | Application context, flow registry/executor, MVC/JSF adapter hoạt động |
| 4 | Form | Bind được giá trị, validation lỗi đúng và không mass assign |
| 5 | Điều hướng | Back/next/cancel và subflow không sai state |
| 6 | Phiên | Timeout, nhiều tab, refresh/back không làm rò dữ liệu |
| 7 | Nghiệp vụ | Xác nhận đơn hàng có kiểm soát trùng và quyền truy cập |

## 13. Checklist kỹ thuật trước khi triển khai

- [ ] Đã phân biệt rõ **2.0–2.4** với **2.5** khi nói về “Web Flow 2.x”.
- [ ] Phiên bản SWF được chọn dựa trên **Spring Framework**, không chỉ dựa vào JDK.
- [ ] JDK build và runtime thỏa baseline, không có bytecode vượt runtime.
- [ ] Servlet container hỗ trợ đúng mức API: với SWF 4 là **Servlet 6.1**.
- [ ] Không trộn `javax.servlet`/`jakarta.servlet` hoặc `javax.faces`/`jakarta.faces`.
- [ ] Spring MVC, Core và Context đồng bộ trong cùng thế hệ.
- [ ] Nếu dùng Boot, đã kiểm tra BOM, starter và SWF version được resolve.
- [ ] Nếu dùng JSF, đã chọn version tối thiểu phù hợp từng dòng Web Flow.
- [ ] Đã kiểm tra version bảo mật và CVE liên quan.
- [ ] Flow đã qua test state/event/transition, subflow, binding/validation, scope/session.
- [ ] Đã thử nhiều tab, timeout, CSRF, quyền truy cập, service exception, submit lặp.
- [ ] Có tài liệu ghi rõ version, dependency tree, môi trường thử nghiệm và kết quả PASS.

## 14. Nguồn tra cứu chính thức

| Tài liệu | Dùng để kiểm tra |
| --- | --- |
| [Spring Web Flow 2.5.1 Reference](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/) | Java 8, Spring 5, Servlet 3.1, lịch sử 2.4–2.5, JSF 2.2 |
| [Spring Web Flow 3.0.2 Reference](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) | Java 17, Spring 6, JSF 4.0, tích hợp MVC/flow |
| [Spring Web Flow 4.0.2 Reference](https://docs.spring.io/spring-webflow/docs/4.0.2/reference/) | Java 17, Spring 7 baseline, Servlet 6.1, JSF 4.1 |
| [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions) | Hỗ trợ JDK, Java EE/Jakarta EE theo dòng Spring |
| [Spring Framework 6 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes) | Bước chuyển Java 17 và `javax` sang `jakarta` |
| [Spring Boot 4 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html) | Spring 7, Java 17, Servlet 6.1 và container |
| [Spring Web Flow Releases](https://github.com/spring-projects/spring-webflow/releases) | Phiên bản phát hành và dependency upgrades |
| [Spring Security Advisory CVE-2026-40985](https://spring.io/security/cve-2026-40985/) | Phiên bản dễ tổn thương và phiên bản sửa lỗi |

**Điểm cần nhớ:** **SWF 2.5 ↔ Spring 5/Java EE**, **SWF 3.0 ↔ Spring 6/Jakarta**, **SWF 4.0 ↔ Spring 7/Servlet 6.1** là ba cặp nền tảng dễ nhớ. Nhánh **2.x trước 2.5** phải tra riêng theo bản cụ thể. Ma trận giúp loại nhanh tổ hợp sai; chỉ dependency tree, bản vá và kiểm thử luồng nhiều bước mới xác nhận được mức sẵn sàng của hệ thống thực tế.
