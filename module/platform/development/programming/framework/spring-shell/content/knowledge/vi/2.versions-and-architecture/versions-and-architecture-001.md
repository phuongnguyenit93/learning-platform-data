# Chọn nhánh Spring Shell theo khả năng tương thích của Spring Boot và Java

Khi thêm Spring Shell vào một ứng dụng Spring Boot, cần chọn phiên bản theo **ma trận tương thích giữa Spring Shell và Spring Boot**, sau đó xác nhận phiên bản Java mà toàn bộ bộ công cụ build và môi trường chạy hỗ trợ. Số major của hai dự án không phải lúc nào cũng trùng nhau: Spring Boot 3.5.x đi cùng Spring Shell 3.4.x, trong khi Spring Boot 4.0.x đi cùng Spring Shell 4.0.x.

Bài viết hướng dẫn cách đọc ma trận, chọn một dòng phiên bản phù hợp cho dự án mới hoặc dự án hiện hữu, cấu hình dependency và kiểm tra lựa chọn trước khi phát hành. Các phiên bản cụ thể bên dưới được đối chiếu tại ngày **26-11-2026**; hãy kiểm tra lại tài liệu chính thức khi bắt đầu một dự án mới vì các nhánh và bản vá tiếp tục thay đổi.

## 1. Hiểu ba lớp tương thích

Một ứng dụng Spring Shell chạy trong nền tảng Spring Boot phải thỏa mãn đồng thời ba lớp sau:

1. **Tương thích Spring Boot – Spring Shell:** Spring Shell phải thuộc dòng được dự án Spring Shell công bố hỗ trợ cho dòng Spring Boot đang dùng. Đây là điều kiện đầu tiên để chọn dependency.
2. **Tương thích với Java:** JDK dùng để biên dịch, phiên bản bytecode được tạo ra và JRE/JDK chạy ứng dụng phải nằm trong phạm vi hỗ trợ của Spring Boot cùng các dependency của Spring Shell.
3. **Tương thích trong đồ thị dependency:** Spring Framework, Spring Boot, JLine và các thư viện liên quan phải được quản lý theo một tập phiên bản nhất quán. Một ứng dụng có thể biên dịch khi ép phiên bản dependency, nhưng điều đó chưa chứng minh tổ hợp ấy được hỗ trợ hoặc hoạt động đúng lúc chạy.

Vì vậy, không nên chọn Spring Shell chỉ bằng cách lấy cùng số major với Spring Boot. Hãy bắt đầu từ phiên bản Spring Boot của ứng dụng, tra dòng Spring Shell tương ứng, rồi mới chọn JDK và bản vá cụ thể.

## 2. Đọc ma trận Spring Boot – Spring Shell

Ma trận tương thích do dự án Spring Shell công bố liệt kê các cặp dòng phiên bản sau:

| Dòng Spring Boot | Dòng Spring Shell tương ứng | Java tối thiểu của Spring Boot | Gợi ý sử dụng |
|---|---|---:|---|
| 4.0.x | 4.0.x | 17 | Ứng dụng dùng Spring Framework 7 và Spring Boot 4.0 |
| 3.5.x | 3.4.x | 17 | Lựa chọn hiện đại khi cần duy trì nền Spring Boot 3 |
| 3.4.x | 3.4.x | 17 | Dự án hiện hữu đang khóa ở Spring Boot 3.4 |
| 3.3.x | 3.3.x | 17 | Dự án cũ cần giữ nguyên dòng Boot 3.3 |
| 3.2.x | 3.2.x | 17 | Chỉ cân nhắc khi nền tảng hiện hữu yêu cầu dòng này |
| 2.7.x | 2.1.x | 8 | Hệ thống cũ cần duy trì Spring Boot 2.7 |

Nguồn của bảng là trang [Spring Boot compatibility của Spring Shell](https://github.com/spring-projects/spring-shell/wiki/Spring-Boot-compatibility). Trang này được cập nhật ngày 27-08-2025 và ghi rõ chỉ hiển thị các phiên bản được hỗ trợ. Bảng giúp xác định **dòng** tương thích; nó không thay thế việc kiểm tra bản vá, Java range và chính sách hỗ trợ tại thời điểm triển khai.

Một vài điểm dễ nhầm:

- Spring Boot 3.5.x sử dụng Spring Shell 3.4.x. Không tự chọn Spring Shell 3.5.x chỉ vì Spring Boot có số minor 3.5.
- Spring Boot 3.4.x cũng sử dụng Spring Shell 3.4.x. Một dòng Spring Shell có thể hỗ trợ nhiều dòng Spring Boot liền kề khi dự án công bố điều đó.
- Spring Boot 4.0.x sử dụng Spring Shell 4.0.x. Spring Shell 4.x dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 trở lên khi tích hợp theo mô hình Spring Boot.
- Không lấy một cặp phiên bản ngoài ma trận rồi kết luận rằng chúng tương thích chỉ vì ứng dụng biên dịch thành công.

### Kiểm tra các dòng mới hơn ma trận

Tại ngày 26-11-2026, tài liệu Spring Boot đã liệt kê Spring Boot 4.2.0 và 4.1.3 là các bản stable. Tuy nhiên, ma trận tương thích Spring Shell được dẫn ở trên vẫn chỉ nêu Spring Boot 4.0.x cho dòng Shell 4.0.x; nó chưa liệt kê Boot 4.1.x hoặc 4.2.x. Spring Shell 4.0.4 cũng cập nhật dependency nền lên Spring Boot 4.0.10 và Spring Framework 7.0.11.

Do đó, nếu dự án bắt buộc dùng Spring Boot 4.1.x hoặc 4.2.x, hãy kiểm tra thông báo phát hành và ma trận tương thích mới nhất của Spring Shell trước khi quyết định. Khi chưa có xác nhận chính thức, xem tổ hợp đó là **chưa được xác minh**; nếu cần thử nghiệm, phải khóa phiên bản rõ ràng và chạy kiểm thử tích hợp trên đúng JDK, thay vì coi đó là một cặp được hỗ trợ mặc định.

## 3. Chọn Java sau khi đã chọn dòng Spring Boot

Phiên bản Java tối thiểu thường được quyết định bởi Spring Boot. Các dòng Boot 3.x và 4.x trong ma trận đều yêu cầu Java 17 trở lên; Spring Boot 2.7.x có thể chạy từ Java 8. Nhưng chỉ biết mức tối thiểu là chưa đủ: từng dòng Boot còn công bố phiên bản Java tối đa đã được kiểm tra tương thích.

Ví dụ với các bản vá hiện hành được tài liệu Spring Boot liệt kê tại thời điểm viết bài:

| Phiên bản Spring Boot | Java tối thiểu | Java tối đa được tài liệu ghi nhận |
|---|---:|---:|
| 4.0.10 | 17 | 27 |
| 3.5.16 | 17 | 25 |
| 3.4.13 | 17 | 24 |
| 3.3.13 | 17 | 23 |
| 2.7.18 | 8 | 21 |

Các con số trên là phạm vi của Spring Boot tương ứng. Thư viện bên thứ ba có thể có yêu cầu riêng hoặc hỗ trợ Java hẹp hơn; tài liệu Spring Boot cũng lưu ý điều này. Khi nâng JDK, hãy kiểm tra release notes của Spring Shell, JLine và các thư viện được ứng dụng sử dụng.

### Phân biệt JDK build, mức bytecode và JDK runtime

Ba giá trị sau có liên quan nhưng không đồng nghĩa:

- **JDK build:** JDK mà Maven hoặc Gradle thực sự dùng để biên dịch và chạy test.
- **Mức Java mục tiêu:** phiên bản bytecode mà compiler tạo ra, thường đặt bằng `java.version`, `maven.compiler.release` hoặc Java toolchain.
- **JDK runtime:** JDK/JRE cài trên máy chủ hoặc môi trường chạy file JAR.

Ví dụ, build bằng JDK 21 nhưng cấu hình bytecode mục tiêu Java 17 có thể phù hợp với runtime Java 17 nếu mọi dependency cũng hỗ trợ Java 17. Ngược lại, chỉ đặt `java.version=17` không giúp ứng dụng chạy trên Java 17 nếu một thư viện đã được biên dịch cho Java 21.

Với ứng dụng mới dùng Spring Boot 3.x hoặc 4.x, Java 17 là mức tối thiểu chung của các dòng trong ma trận. Có thể chọn một LTS mới hơn nếu toàn bộ dòng Boot, Spring Shell, dependency và môi trường triển khai đều hỗ trợ. Với hệ thống Boot 2.7, đừng nâng JDK độc lập mà chưa kiểm tra các thư viện cũ và pipeline triển khai.

## 4. Quy trình chọn phiên bản cho dự án

Thực hiện theo thứ tự sau để tránh phải xử lý nhiều xung đột dependency cùng lúc.

### Bước 1: Xác định phiên bản Spring Boot thực tế

Kiểm tra `pom.xml`, `build.gradle` hoặc `build.gradle.kts`. Với Maven, tìm `spring-boot-starter-parent`, `spring-boot-dependencies` hoặc property đang quản lý phiên bản Boot. Với Gradle, kiểm tra plugin `org.springframework.boot` và cấu hình dependency management.

Nếu dự án đã tồn tại, giữ nguyên dòng Boot trong lần chọn Spring Shell đầu tiên. Nếu dự án đang ở Boot 3.5.x, tra Shell 3.4.x; nếu đang ở Boot 4.0.x, tra Shell 4.0.x. Chỉ lên kế hoạch nâng Boot khi đã đánh giá riêng các thay đổi của nền tảng.

### Bước 2: Tra dòng Spring Shell tương ứng

Đối chiếu bảng tương thích chính thức. Sau khi biết dòng, chọn bản vá ổn định mới nhất thuộc dòng đó và kiểm tra release notes. Không sử dụng bản `SNAPSHOT`, milestone hoặc release candidate cho môi trường production trừ khi dự án chủ động chấp nhận trạng thái thử nghiệm.

Tại ngày 26-11-2026, Spring Shell 4.0.4 là bản phát hành mới nhất của dòng 4.0; bản này được công bố ngày 19-11-2026. Dòng 4.x chuyển sang chế độ bảo trì và dự kiến nhận sửa lỗi, cập nhật bảo mật, cập nhật dependency đến tháng 12-2027. Với dòng 3.4, bản 3.4.3 được công bố cùng đợt phát hành tháng 6-2026. Hãy kiểm tra trang Releases để xác nhận bản vá mới nhất ngay trước khi khóa phiên bản.

### Bước 3: Kiểm tra JDK và công cụ build

Chạy các lệnh sau trong đúng terminal và môi trường build của dự án:

```bash
java -version
./mvnw -version
```

Với Gradle, có thể kiểm tra thêm:

```bash
./gradlew --version
```

Đối chiếu JDK thực tế với yêu cầu của Spring Boot và các dependency. Trên Windows, dùng `mvnw.cmd` hoặc `gradlew.bat` tương ứng. Không chỉ kiểm tra JDK trên máy lập trình; pipeline CI và máy chạy production cũng phải dùng phiên bản tương thích.

### Bước 4: Khóa dependency theo một nguồn quản lý

Trong ứng dụng Spring Boot, ưu tiên dùng Spring Boot parent/BOM và Spring Shell starter. Khai báo phiên bản Spring Shell tường minh nếu BOM của dự án không quản lý phiên bản đó. Tránh tự nâng riêng Spring Framework, Reactor, JLine hoặc các thư viện nền chỉ để xử lý một lỗi build; trước tiên hãy xem phiên bản mà release Spring Shell và BOM Spring Boot đã chọn.

### Bước 5: Build và kiểm tra hành vi thực tế

Sau khi thêm dependency, chạy build và test trên JDK mục tiêu. Kiểm tra dependency tree để phát hiện nhiều phiên bản Spring Framework hoặc Spring Boot cùng xuất hiện:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:*,org.springframework:*,org.springframework.shell:*
```

Tiếp đó, chạy JAR đã đóng gói trong môi trường tương đương production. Tối thiểu hãy xác nhận ứng dụng khởi động, lệnh mẫu đăng ký và thực thi đúng, trợ giúp hiển thị đúng, đối số được parse đúng và mã thoát phản ánh kết quả. Nếu ứng dụng hỗ trợ interactive mode, script hoặc native image, hãy kiểm tra thêm các chế độ đó vì một build thành công chưa xác minh được hành vi terminal.

## 5. Ví dụ cấu hình Maven

Ví dụ dưới đây dùng Spring Boot 4.0.10, Spring Shell 4.0.4 và Java 21. Đây là cặp thuộc dòng tương thích Boot 4.0.x – Shell 4.0.x; Java 21 nằm trong phạm vi Spring Boot 4.0.10 công bố.

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.0.10</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
    <spring-shell.version>4.0.4</spring-shell.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter</artifactId>
        <version>${spring-shell.version}</version>
    </dependency>
</dependencies>
```

Nếu ứng dụng vẫn dùng Spring Boot 3.5.x, hãy chọn Spring Shell 3.4.x theo ma trận, ví dụ dòng dependency `spring-shell-starter` với phiên bản 3.4.3 và parent Spring Boot 3.5.x. Không thay riêng version Spring Shell thành 4.0.x trong cấu hình Boot 3.5.x: Spring Shell 4.x yêu cầu nền Spring Boot 4 khi tích hợp theo mô hình này.

Với Gradle, có thể khóa JDK bằng toolchain để máy lập trình và CI dùng cùng ngôn ngữ biên dịch:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Khai báo toolchain giúp kiểm soát JDK build; vẫn cần bảo đảm runtime production có phiên bản Java phù hợp.

## 6. Lưu ý khi nâng từ Spring Shell 3 lên 4

Nâng Spring Shell 3 lên 4 là một lần nâng major có thay đổi API và cách tích hợp. Hướng dẫn migration của dự án khuyến nghị nâng ứng dụng lên Spring Shell 3.4.x mới nhất trước khi chuyển sang 4.x. Spring Shell 4 dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 trở lên cho tích hợp Spring Boot.

Một thay đổi về cấu trúc dependency cần nhớ: module `spring-shell-core` của 4.x không còn phụ thuộc trực tiếp vào Spring Boot. Nếu tích hợp Spring Shell vào ứng dụng Boot, hãy dùng một Spring Shell starter hoặc bổ sung module `spring-shell-core-autoconfigure` theo hướng dẫn. Không bê nguyên cấu hình dependency của 3.x sang 4.x mà không đọc migration guide.

Quy trình nâng cấp nên diễn ra theo từng bước:

1. Nâng Spring Shell 3.x hiện tại lên bản vá 3.4.x mới nhất phù hợp với Boot 3.x.
2. Đọc migration guide 4.x và ghi nhận các API, command model, test utility hoặc cấu hình đã thay đổi.
3. Nâng Spring Boot lên một dòng Boot 4.x được Spring Shell công bố hỗ trợ.
4. Nâng Spring Shell lên 4.x, sửa mã nguồn và test theo migration guide.
5. Chạy lại kiểm thử command, interactive mode, script, terminal provider và đóng gói trên JDK mục tiêu.

## 7. Các lỗi chọn phiên bản thường gặp

| Lựa chọn hoặc thao tác | Vấn đề có thể gặp | Cách xử lý |
|---|---|---|
| Chọn Shell 3.5.x cho Boot 3.5.x vì trùng số minor | Không theo cặp được công bố trong ma trận | Dùng Shell 3.4.x cho Boot 3.5.x |
| Dùng Shell 4.0.x với Boot 3.x | Không đáp ứng yêu cầu nền Spring Boot 4 của Shell 4 | Nâng Boot theo kế hoạch migration hoặc giữ Shell 3.x tương ứng |
| Dùng Shell 3.4.x với Boot 4.0.x | Chọn sai dòng so với ma trận | Dùng Shell 4.0.x cho Boot 4.0.x |
| Dùng Boot 4.2.x và mặc định cho rằng Shell 4.0.4 đã hỗ trợ | Ma trận Spring Shell hiện chưa liệt kê Boot 4.2.x | Kiểm tra xác nhận mới nhất hoặc xem tổ hợp là chưa được xác minh |
| Build bằng JDK mới nhưng chạy trên JDK cũ | Có thể gặp lỗi phiên bản class hoặc dependency không hỗ trợ runtime | Đồng bộ JDK build, mức bytecode và JDK runtime |
| Ép một phiên bản Spring Framework riêng lẻ | Có thể tạo đồ thị dependency không nhất quán với BOM | Dùng BOM/parent phù hợp và kiểm tra `dependency:tree` |

## 8. Checklist trước khi chốt phiên bản

- [ ] Đã xác định chính xác dòng và bản vá Spring Boot của ứng dụng.
- [ ] Đã tra ma trận tương thích chính thức để chọn dòng Spring Shell.
- [ ] Đã chọn bản phát hành ổn định mới nhất phù hợp và đọc release notes.
- [ ] JDK build, mức bytecode và JDK runtime đều nằm trong phạm vi hỗ trợ.
- [ ] CI dùng cùng cấu hình JDK và build tool như cấu hình đã xác minh.
- [ ] Dependency tree không có các phiên bản Spring Boot/Spring Framework xung đột.
- [ ] Đã chạy test, đóng gói và thử lệnh Spring Shell trong môi trường mục tiêu.
- [ ] Nếu nâng major hoặc dùng dòng chưa có trong ma trận, đã đối chiếu migration guide và ghi nhận kết quả kiểm thử.

## Tài liệu tham khảo

1. [Spring Shell – Spring Boot compatibility](https://github.com/spring-projects/spring-shell/wiki/Spring-Boot-compatibility) – ma trận dòng phiên bản được công bố.
2. [Spring Shell – v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) – yêu cầu nền tảng và các thay đổi khi nâng từ 3.x lên 4.x.
3. [Spring Shell releases](https://github.com/spring-projects/spring-shell/releases) và [Spring Shell 4.0.4 available now](https://spring.io/blog/2026/11/19/spring-shell-4-0-4-available-now/) – bản phát hành, dependency cập nhật và trạng thái bảo trì.
4. [Spring Boot 4.0 system requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html), [3.5](https://docs.spring.io/spring-boot/3.5/system-requirements.html), [3.4](https://docs.spring.io/spring-boot/3.4/system-requirements.html), [3.3](https://docs.spring.io/spring-boot/3.3/system-requirements.html) và [2.7](https://docs.spring.io/spring-boot/docs/2.7.x/reference/html/getting-started.html) – yêu cầu Java theo từng dòng Spring Boot.

Khi tài liệu giữa các dự án thay đổi ở thời điểm khác nhau, hãy ưu tiên release notes và ma trận tương thích mới nhất của Spring Shell cùng system requirements của đúng bản Spring Boot đang dùng. Ghi lại phiên bản đã kiểm tra trong cấu hình build để lần nâng cấp tiếp theo có thể tái lập và đánh giá được.
