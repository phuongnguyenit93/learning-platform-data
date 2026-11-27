# Đối chiếu Spring Boot compatibility matrix

Khi thêm Spring Modulith vào một ứng dụng Spring Boot, cần chọn release train tương thích với thế hệ Spring Boot mà ứng dụng đang sử dụng. Hai dự án phát hành phiên bản độc lập: Spring Boot có phiên bản riêng, Spring Modulith có phiên bản riêng. Vì vậy, không thể suy ra phiên bản Modulith chỉ bằng cách sao chép số phiên bản Boot.

Compatibility matrix của Spring Modulith giúp xác định baseline Spring Boot mà một release train được biên dịch cùng và các phiên bản mà ví dụ của dự án đã được kiểm thử. Việc đọc đúng hai cột này giúp tránh nhầm lẫn giữa baseline kỹ thuật và phạm vi kiểm thử ví dụ.

## 1. Phân biệt compiled against và examples tested against

Phụ lục tương thích của Spring Modulith có hai cột liên quan trực tiếp tới Spring Boot:

| Cột | Ý nghĩa |
|---|---|
| Spring Boot Version (compiled against) | Phiên bản nền mà release train Spring Modulith được biên dịch và phát triển tương ứng |
| Spring Boot Version (examples tested against) | Các phiên bản Spring Boot mà ví dụ trong tài liệu được chạy kiểm thử |

Hai cột này không có cùng ý nghĩa. Ví dụ, Spring Modulith 1.4 được biên dịch với Spring Boot 3.5, trong khi ví dụ của nó được kiểm thử trên các phiên bản Boot 3.1 đến 3.5. Điều đó không có nghĩa mọi tổ hợp thư viện, plugin và dependency của ứng dụng đều được bảo đảm tương thích như nhau trên toàn bộ dải phiên bản.

Khi chọn phiên bản cho dự án mới, ưu tiên release train được xây dựng cho thế hệ Spring Boot mà ứng dụng đang dùng. Cột examples tested against là thông tin bổ sung về phạm vi kiểm thử của tài liệu, không nên được diễn giải thành cam kết hỗ trợ mọi tổ hợp có thể.

## 2. Ghép Spring Boot generation với Spring Modulith release train

Bảng dưới đây tóm tắt các cặp release train theo baseline Spring Boot. Với các dòng 1.x, baseline được ghi trong Appendix A. Với các dòng 2.x, cần kết hợp thông tin phát hành GA của từng thế hệ vì bảng Appendix A hiện hành vẫn còn một dòng snapshot cũ.

| Spring Boot generation | Spring Modulith release train phù hợp | Baseline được công bố |
|---|---|---|
| 4.2.x | 2.2.x | Spring Modulith 2.2 được build với Boot 4.2 và Framework 7.1 |
| 4.1.x | 2.1.x | 2.1 chuyển sang Boot 4.1 |
| 4.0.x | 2.0.x | 2.0 đặt baseline Boot 4 và Framework 7 |
| 3.5.x | 1.4.x | 1.4 được biên dịch với Boot 3.5 |
| 3.4.x | 1.3.x | 1.3 được biên dịch với Boot 3.4 |
| 3.3.x | 1.2.x | 1.2 được biên dịch với Boot 3.3 |
| 3.2.x | 1.1.x | 1.1 được biên dịch với Boot 3.2 |

Đây là cách ghép theo release train và baseline, không phải lời khẳng định rằng mọi patch release đều có thể trộn tùy ý. Với ứng dụng đang dùng một patch version cụ thể, hãy kiểm tra release notes và dependency management của đúng phiên bản trước khi nâng cấp.

Ví dụ về các bản phát hành ổn định tại ngày 27/11/2026:

| Release train | Bản phát hành được công bố |
|---|---|
| Spring Modulith 2.2 | `2.2.0` GA |
| Spring Modulith 2.1 | `2.1.3` |
| Spring Modulith 2.0 | `2.0.10` |

Với ứng dụng Spring Boot 4.2, Spring Modulith 2.2.0 là release train mới nhất tại thời điểm này. Với ứng dụng vẫn ở Boot 4.1 hoặc 4.0, chọn nhánh Modulith tương ứng thay vì nâng riêng Modulith lên 2.2 trong khi giữ nguyên Boot cũ.

## 3. Lưu ý về bảng Appendix A hiện hành

Trang Appendix của Spring Modulith có tiêu đề phiên bản 2.2.0, nhưng bảng Appendix A tại thời điểm biên soạn vẫn hiển thị dòng `2.0 (snapshot)` được biên dịch với `4.0 SNAPSHOT`. Dòng đó là thông tin snapshot cũ, không phản ánh baseline của Spring Modulith 2.2 GA.

Để đối chiếu release train 2.x, cần đọc thông báo GA tương ứng:

- Spring Modulith 2.0 GA xác nhận dự án nâng baseline lên Spring Boot 4 và Spring Framework 7.
- Spring Modulith 2.1 M1 chuyển sang Spring Boot 4.1; bản 2.1 GA tiếp tục thuộc thế hệ đó.
- Spring Modulith 2.2 GA được build với Spring Boot 4.2 và Spring Framework 7.1.

Vì vậy, không sao chép nguyên dòng snapshot trong Appendix A rồi kết luận Spring Modulith 2.2 dùng Boot 4.0. Khi tài liệu tổng quan và thông báo phát hành không đồng bộ, dùng release notes GA mới nhất để xác định baseline của release train và ghi nhận rõ nguồn đối chiếu.

## 4. Đọc bảng 1.x chi tiết

Appendix A công bố các baseline và phạm vi ví dụ đã kiểm thử cho các release train 1.x như sau:

| Spring Modulith | Boot compiled against | Boot examples tested against | jMolecules compiled |
|---|---:|---|---:|
| 1.4 | 3.5 | 3.1, 3.2, 3.3, 3.4, 3.5 | 2023.2 |
| 1.3 | 3.4 | 3.1, 3.2, 3.3, 3.4, 3.5 | 2023.1 |
| 1.2 | 3.3 | 3.1, 3.2, 3.3, 3.4 | 2023.1 |
| 1.1 | 3.2 | 3.1, 3.2, 3.3, 3.4 | 2023.1 |

Ma trận còn ghi các phiên bản jMolecules đã được kiểm thử riêng. Nếu ứng dụng sử dụng jMolecules, cần xem cả cột compiled và tested của jMolecules, không chỉ kiểm tra Spring Boot. Khi dự án không dùng jMolecules, cột này không phải yếu tố quyết định cho việc chọn release train Modulith.

Ví dụ: một ứng dụng Boot 3.5 nên bắt đầu với Modulith 1.4 vì đây là release train được biên dịch cùng Boot 3.5. Mặc dù ví dụ của Modulith 1.3 đã được kiểm thử trên Boot 3.5, điều đó không làm thay đổi baseline 3.4 của nhánh 1.3.

## 5. Vì sao Spring Modulith 2.x yêu cầu thế hệ Boot 4?

Spring Modulith 2.0 là major release có thay đổi baseline nền tảng. Dự án nâng lên Spring Boot 4 và Spring Framework 7. Các release train tiếp theo trong dòng 2.x tiếp tục theo các thế hệ Boot 4 tương ứng:

```text
Spring Boot 4.0  ──> Spring Modulith 2.0
Spring Boot 4.1  ──> Spring Modulith 2.1
Spring Boot 4.2  ──> Spring Modulith 2.2

Spring Boot 3.5  ──> Spring Modulith 1.4
Spring Boot 3.4  ──> Spring Modulith 1.3
Spring Boot 3.3  ──> Spring Modulith 1.2
Spring Boot 3.2  ──> Spring Modulith 1.1
```

Không nên coi major version của Modulith chỉ là số tính năng. Khi baseline Boot hoặc Framework thay đổi, API nền, auto-configuration, dependency transitive và cách tích hợp có thể thay đổi theo. Nâng từ Modulith 1.x lên 2.x thường cần đánh giá như một bước nâng nền tảng Spring Boot, không chỉ là đổi một con số trong dependency.

Nếu ứng dụng đang ở Boot 3.5 và chưa có kế hoạch nâng Boot 4, hãy dùng nhánh Modulith 1.4 phù hợp. Khi muốn chuyển sang Modulith 2.x, hãy lập kế hoạch nâng Boot 4, Framework 7 và kiểm tra các migration note liên quan trước.

## 6. Dùng Spring Modulith BOM để đồng bộ artifact

Spring Modulith gồm nhiều artifact riêng, ví dụ `spring-modulith-core`, `spring-modulith-events-jdbc`, `spring-modulith-events-jpa`, `spring-modulith-docs` và `spring-modulith-test`. Một ứng dụng có thể dùng nhiều artifact cùng lúc. Nếu tự gán version cho từng artifact, rất dễ tạo ra tổ hợp lệch release train.

Spring Modulith cung cấp BOM `spring-modulith-bom` để quản lý version của các artifact thuộc cùng một release train. Hãy khai báo BOM một lần rồi bỏ version ở các dependency Modulith riêng lẻ.

### Maven

Ví dụ ứng dụng dùng Spring Boot 4.2 và Spring Modulith 2.2.0:

```xml
<properties>
    <spring-modulith.version>2.2.0</spring-modulith.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>${spring-modulith.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-core</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Spring Boot parent hoặc `spring-boot-dependencies` BOM tiếp tục quản lý dependency nền tảng của Boot. Spring Modulith BOM quản lý các artifact Modulith. Hai BOM có trách nhiệm bổ sung cho nhau.

### Gradle Kotlin DSL

```kotlin
dependencies {
    implementation(platform("org.springframework.modulith:spring-modulith-bom:2.2.0"))

    implementation("org.springframework.modulith:spring-modulith-starter-core")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}
```

Nếu dùng Gradle Groovy DSL, cách khai báo tương đương:

```groovy
dependencies {
    implementation platform('org.springframework.modulith:spring-modulith-bom:2.2.0')

    implementation 'org.springframework.modulith:spring-modulith-starter-core'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}
```

Thay `2.2.0` bằng release train tương ứng với Spring Boot của ứng dụng. Không khai báo một version Modulith ở BOM và một version khác trên từng artifact, trừ khi đang thực hiện một thử nghiệm dependency có kiểm soát.

## 7. Chọn starter và artifact theo tính năng

Spring Modulith cho phép dùng từng artifact riêng hoặc starter để khai báo nhóm chức năng phổ biến. Một số lựa chọn:

| Nhu cầu | Artifact/starter thường dùng |
|---|---|
| Module model và runtime core | `spring-modulith-starter-core` |
| Kiểm thử application module | `spring-modulith-starter-test` ở test scope |
| Event Publication Registry dùng JDBC | `spring-modulith-starter-jdbc` |
| Event Publication Registry dùng JPA | `spring-modulith-starter-jpa` |
| Event Publication Registry dùng MongoDB | `spring-modulith-starter-mongodb` |
| Sinh PlantUML và tài liệu module | `spring-modulith-docs` ở test scope; starter test cũng bao gồm artifact này |
| Actuator support cho module structure | `spring-modulith-starter-insight` ở runtime scope |

Không cần thêm tất cả starter. Chọn đúng nhóm tính năng mà ứng dụng sử dụng và để BOM quản lý version của chúng. Khi thêm một persistence starter cho event registry, cũng cần cấu hình database và transaction phù hợp với implementation đã chọn.

## 8. Kiểm tra dependency tree khi gặp lỗi tương thích

Nếu build gặp `NoSuchMethodError`, `ClassNotFoundException`, lỗi auto-configuration hoặc API không tồn tại, hãy kiểm tra dependency tree trước khi thay đổi code.

Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.modulith
```

Gradle:

```bash
./gradlew dependencyInsight \
    --dependency spring-modulith \
    --configuration runtimeClasspath
```

Kiểm tra cả `compileClasspath` và `runtimeClasspath` nếu lỗi chỉ xảy ra trong compile hoặc startup. Tìm các dấu hiệu:

- Artifact Modulith cùng group có version khác nhau.
- Một starter kéo về phiên bản transitive không cùng release train với BOM dự kiến.
- Có dependency khai báo version trực tiếp ghi đè version được BOM quản lý.
- Dự án dùng Boot 3.x nhưng dependency Modulith 2.x, hoặc dùng Boot 4.x nhưng dependency Modulith 1.x.
- Plugin hoặc thư viện tích hợp khác yêu cầu một thế hệ Spring Framework không tương thích.

Sau khi xác định nguyên nhân, chỉnh dependency management tại một điểm tập trung. Tránh thêm nhiều exclusion hoặc pin version rời rạc nếu chưa hiểu dependency nào đang kéo phiên bản không mong muốn.

## 9. Quy trình nâng cấp release train

Khi nâng Spring Boot hoặc Spring Modulith, thực hiện theo trình tự có kiểm soát:

1. **Xác định baseline hiện tại:** ghi nhận phiên bản Spring Boot, Spring Framework, Spring Modulith và các starter đang dùng.
2. **Tra compatibility matrix:** chọn release train Modulith được biên dịch cùng thế hệ Boot mục tiêu.
3. **Đọc release notes:** kiểm tra thay đổi major/minor, migration note và các dependency nền tảng được nâng cấp.
4. **Cập nhật BOM:** thay một version Modulith tại dependency management, không cập nhật rời từng artifact.
5. **Kiểm tra dependency tree:** xác nhận các artifact Modulith cùng release train và không bị version override.
6. **Chạy kiểm tra phù hợp:** compile, unit test, architecture test, module integration test và kiểm tra startup trong môi trường phát triển.
7. **Kiểm tra persistence/event integration:** nếu dùng JDBC, JPA, MongoDB hoặc externalization, xác nhận schema và transaction behavior phù hợp với release mới.
8. **Ghi lại baseline mới:** cập nhật tài liệu kỹ thuật để lần nâng cấp tiếp theo có mốc đối chiếu rõ.

Không nên nâng Boot và Modulith theo hai đợt không có kiểm soát dependency. Nếu thay đổi cả hai cùng lúc, giữ chúng trong cùng một nhánh release train và dùng test để phân biệt lỗi do nền tảng Boot với lỗi do thay đổi Modulith.

## 10. Những lỗi thường gặp khi đọc compatibility matrix

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Boot 4.2 nghĩa là Modulith 4.2 | Hai dự án có version độc lập; Boot 4.2 ghép với Modulith 2.2 |
| Dùng Modulith mới nhất cho mọi Boot | Chọn release train theo baseline Boot; không chỉ chọn số lớn nhất |
| Examples tested against là compiled against | Đây là hai thông tin khác nhau trong Appendix A |
| Một ví dụ chạy trên Boot 3.5 chứng minh mọi artifact 1.3 tương thích đầy đủ | Hãy ưu tiên baseline 3.4 của Modulith 1.3 và release train 1.4 cho Boot 3.5 |
| Appendix A luôn phản ánh mọi GA mới nhất | Kiểm tra ngày cập nhật và đối chiếu release announcement; bảng hiện hành còn dòng 2.0 snapshot cũ dù 2.2 đã GA |
| Chỉ cần đồng bộ `spring-modulith-core` | Các artifact Modulith khác cũng cần cùng release train; dùng BOM để quản lý |
| Spring Modulith BOM thay thế Spring Boot BOM | Mỗi BOM quản lý một nhóm dependency khác nhau |
| Build thành công đồng nghĩa runtime tương thích | Cần kiểm tra startup, auto-configuration, persistence và integration test |

## 11. Checklist chọn phiên bản

- [ ] Đã xác định chính xác Spring Boot major/minor của ứng dụng.
- [ ] Đã chọn Spring Modulith release train theo baseline Boot tương ứng.
- [ ] Đã phân biệt cột compiled against và examples tested against.
- [ ] Đã kiểm tra release notes của phiên bản GA mục tiêu.
- [ ] Đã lưu ý các dòng snapshot hoặc dữ liệu cũ trong compatibility matrix.
- [ ] Đã khai báo `spring-modulith-bom` một lần trong dependency management.
- [ ] Các artifact Modulith không tự khai báo version xung đột với BOM.
- [ ] Spring Boot BOM và Spring Modulith BOM vẫn được quản lý riêng theo trách nhiệm của chúng.
- [ ] Đã kiểm tra dependency tree khi có version conflict hoặc lỗi classpath.
- [ ] Đã kiểm tra compile, architecture test, module integration test và startup sau nâng cấp.

Compatibility matrix giúp chọn đúng release train cho nền tảng Spring Boot. Khi kết hợp baseline được biên dịch, phạm vi ví dụ đã kiểm thử, release notes và Spring Modulith BOM, nhóm có thể giữ các artifact cùng thế hệ, giảm lỗi classpath và lên kế hoạch nâng cấp có kiểm soát.

## Tài liệu tham khảo

- [Spring Modulith – Appendix A: Spring Boot Compatibility](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Spring Modulith – Using Spring Modulith and the BOM](https://docs.spring.io/spring-modulith/reference/)
- [Spring Boot – Spring Project Version Mappings](https://spring.io/projects/generations/)
- [Spring Modulith 2.2 GA, 2.1.3, and 2.0.10 released – November 19, 2026](https://spring.io/blog/2026/11/19/spring-modulith-2-2-ga-2-1-3-and-2-0-10-released/)
- [Spring Modulith 2.1 GA – June 11, 2026](https://spring.io/blog/2026/06/11/spring-modulith-2-1-ga-2-0-7-and-1-4-12-released/)
- [Spring Modulith 2.0 GA – November 21, 2025](https://spring.io/blog/2025/11/21/spring-modulith-2-0-ga-1-4-5-and-1-3-11-released/)
- [Spring Modulith 1.4 GA – May 28, 2025](https://spring.io/blog/2025/05/28/spring-modulith-1-4-1-3-6-and-1-2-13-released/)
