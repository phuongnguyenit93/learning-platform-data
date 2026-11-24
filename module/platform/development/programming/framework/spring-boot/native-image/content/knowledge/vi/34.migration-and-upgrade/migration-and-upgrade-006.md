# Đối chiếu hướng dẫn nâng cấp Spring Boot, Framework, GraalVM và Native Build Tools

## 1. Vì sao phải đối chiếu nhiều hướng dẫn?

Nâng cấp một ứng dụng Spring Boot Native Image thường liên quan nhiều thành phần có vòng đời phát hành riêng: Spring Boot, Spring Framework, JDK, GraalVM Native Image, Gradle/Maven, Spring Boot plugin, GraalVM Native Build Tools, buildpacks và native compiler/linker. Mỗi thành phần có thể công bố yêu cầu JDK, phiên bản tối thiểu, giới hạn tương thích và thay đổi hành vi khác nhau.

Một phiên bản Spring Boot mới có thể yêu cầu JDK mới hơn; một phiên bản GraalVM mới có thể thay đổi cách cài Native Image hoặc hỗ trợ target; plugin build có thể yêu cầu Gradle/Maven tối thiểu; còn Spring Framework có thể thay đổi AOT API mà thư viện tích hợp đang sử dụng. Nâng từng version riêng lẻ mà không kiểm tra cả tổ hợp có thể dẫn đến lỗi compile, AOT processing, native compilation hoặc runtime.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, mục tiêu của việc đọc hướng dẫn nâng cấp là xác định một tổ hợp được hỗ trợ và có thể kiểm thử, không phải chỉ chọn version mới nhất cho từng thành phần.

## 2. Bản đồ các thành phần cần đối chiếu

| Thành phần | Tài liệu cần xem | Câu hỏi chính |
|---|---|---|
| Spring Boot | System requirements, release notes, migration guide | JDK tối thiểu? Framework version nào được quản lý? Breaking changes nào? |
| Spring Framework | What's new, upgrade guide, AOT/native docs | AOT API, bean processing, hints hoặc proxy có đổi không? |
| JDK | Release notes, support policy, toolchain docs | Java release/patch nào được hỗ trợ? Có thay đổi compiler/runtime không? |
| GraalVM | Release notes, compatibility matrix, Native Image docs | JDK baseline, OS/architecture, libc và Native Image options? |
| Native Build Tools | Plugin release notes và compatibility docs | Gradle/Maven version, Spring Boot integration, task/goal thay đổi? |
| Gradle/Maven | Compatibility matrix và wrapper release notes | Build tool chạy trên JDK nào? Plugin yêu cầu version nào? |
| Native compiler/linker | GraalVM/toolchain docs | Compiler, linker, SDK và system libraries cần gì? |
| Buildpacks/container | Builder/run image release notes | Builder, lifecycle, run image và target ABI có tương thích? |

Không dùng một tài liệu duy nhất để kết luận toàn bộ stack tương thích. Mỗi nhà cung cấp chịu trách nhiệm cho phần sản phẩm của họ; cần đối chiếu các điều kiện giao nhau.

## 3. Phân biệt minimum, supported và tested

Ba khái niệm thường bị nhầm:

- **Minimum requirement**: phiên bản thấp nhất được tài liệu nêu là cần thiết để chạy hoặc build.
- **Supported combination**: tổ hợp version nằm trong phạm vi nhà cung cấp hỗ trợ.
- **Tested combination**: tổ hợp đã được chính dự án/đội ngũ chạy qua pipeline kiểm thử.

JDK tối thiểu của Spring Boot không tự động chứng minh mọi GraalVM distribution có cùng JDK major đều tương thích. Plugin có thể yêu cầu Gradle mới hơn; một dependency native có thể chỉ hỗ trợ một số OS/architecture.

Tạo bảng kiểm soát:

| Lớp | Minimum | Chọn dùng | Evidence |
|---|---|---|---|
| JDK | Theo Spring Boot/plugin | Version cụ thể và vendor | Build toolchain log |
| Spring Boot | Theo ứng dụng | Patch release được hỗ trợ | Release notes/migration guide |
| Spring Framework | Theo Boot BOM hoặc override đã kiểm tra | Version tương ứng | Dependency report |
| GraalVM | Theo Native Image support | Distribution/version cụ thể | Native Image version output |
| Native Build Tools | Theo plugin compatibility | Version cụ thể | Plugin docs/build log |
| Gradle/Maven | Theo plugin requirements | Wrapper version | Wrapper properties |
| Builder image | Theo native toolchain | Tag và digest | Image manifest |

Ghi URL/tên tài liệu, ngày truy cập hoặc release được tham chiếu, và commit cập nhật bảng. Điều này giúp reviewer biết kết luận tương thích dựa trên bằng chứng nào.

## 4. Bắt đầu từ Spring Boot release notes

Khi nâng Spring Boot:

1. Xác định version hiện tại và version đích.
2. Đọc system requirements của version đích.
3. Đọc release notes cho mọi minor/major version nằm giữa.
4. Đọc migration guide và deprecated API notes.
5. Xác định Spring Framework version được Spring Boot quản lý.
6. Kiểm tra JDK baseline, Gradle/Maven plugin requirements.
7. Kiểm tra thay đổi auto-configuration, properties và test infrastructure.
8. Build lại ứng dụng JVM trước khi thêm Native Image vào phạm vi.

Spring Boot BOM/parent quản lý một tập dependency đã được kiểm thử cùng release. Nếu override Spring Framework hoặc thư viện nền tảng, phải kiểm tra compatibility riêng và ghi lý do. Không nâng riêng Spring Framework chỉ để lấy một fix mà không đánh giá BOM và auto-configuration.

## 5. Đọc Spring Framework migration guide với góc nhìn AOT

Spring Framework có thể thay đổi API/configuration liên quan:

- ApplicationContext và bean definition processing.
- RuntimeHints, RuntimeHintsRegistrar và reflection metadata.
- Proxy/AOP generation.
- Resource handling.
- Serialization và binding.
- Classpath scanning và condition evaluation.
- TestContext và AOT test support.

Khi nâng Spring Boot, thường Framework version cũng đổi theo BOM. Đọc phần What's New và upgrade guide của Framework version tương ứng, tập trung vào API mà ứng dụng hoặc thư viện custom đang dùng.

Tìm các dấu hiệu trong codebase: implementation của RuntimeHintsRegistrar, custom BeanFactoryPostProcessor, BeanDefinitionRegistryPostProcessor, custom condition, proxy configuration và resource loader. Những extension can thiệp sâu vào context có thể cần điều chỉnh khi AOT engine thay đổi.

Không chỉ kiểm tra compile. Một API có thể vẫn compile nhưng hành vi AOT hoặc generated bean graph thay đổi.

## 6. Đối chiếu JDK và GraalVM distribution

GraalVM có nhiều distribution/release line và có thể đóng gói theo cách khác nhau. Khi đọc tài liệu, xác định rõ:

- GraalVM distribution/vendor.
- JDK major và patch version.
- Native Image component/version.
- Cách cài đặt Native Image.
- OS và CPU architecture.
- glibc/musl hoặc ABI target.
- Native compiler/linker requirements.
- Hỗ trợ build trong container và cross-compilation nếu cần.

Không suy ra rằng GraalVM có cùng JDK major sẽ có cùng Native Image options hoặc compatibility. Các distribution có thể khác thành phần, license/feature và packaging.

Kiểm tra version thực tế trong CI:

```bash
java -version
native-image --version
native-image --help
```

Lưu output này vào build manifest. Nếu dùng container builder, lưu cả image digest và platform, không chỉ tag.

## 7. Đối chiếu GraalVM Native Image release notes

Mỗi lần nâng GraalVM/Native Image, rà soát:

- Option đã deprecated, đổi tên hoặc bị loại.
- Thay đổi reachability analysis và default behavior.
- Runtime initialization/build-time initialization.
- Reflection, JNI, serialization và resource metadata.
- PGO/profile-guided optimization nếu đang sử dụng.
- Debug information và diagnostic options.
- Static/dynamic linking, libc và target support.
- Compiler/linker và memory requirement.
- Build time, executable size và runtime behavior.

Một option từng hoạt động có thể thay đổi semantics hoặc trở thành mặc định. Không sao chép toàn bộ native-image arguments từ build cũ sang version mới mà không đọc release notes và kiểm tra --help.

Với lỗi compilation, giữ command line và full compiler log để đối chiếu thay đổi. Với lỗi runtime, giữ binary identity, stack trace và runtime image digest.

## 8. Đối chiếu Native Build Tools plugin

Native Build Tools kết nối Gradle/Maven với Native Image compiler. Khi nâng plugin, đọc:

- Plugin version và JDK requirement.
- Gradle/Maven minimum version.
- Task/goal names và lifecycle integration.
- Cách truyền build arguments.
- Cấu hình toolchain và GraalVM detection.
- Test support và native test execution.
- Container/buildpack integration nếu có.
- Thay đổi defaults và deprecations.

Plugin version không nhất thiết phải trùng GraalVM version. Chọn theo compatibility docs của plugin và GraalVM, rồi xác minh trong pipeline. Nếu Spring Boot plugin đã quản lý hoặc tích hợp Native Build Tools, tránh thêm plugin thứ hai theo cách tạo hai cấu hình cạnh tranh.

## 9. Kiểm tra Gradle/Maven compatibility

Gradle Wrapper hoặc Maven Wrapper cần tương thích với JDK chạy build và plugin được áp dụng.

Gradle:

```bash
./gradlew --version
./gradlew tasks
./gradlew buildEnvironment
```

Maven:

```bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:tree
```

Đọc compatibility matrix của Gradle/Maven để kiểm tra Java runtime hỗ trợ chạy build tool; phân biệt điều đó với Java toolchain dùng để compile application. Ví dụ, Gradle daemon có thể chạy bằng một JDK trong khi toolchain compile chọn JDK khác. Native Build Tools có thể sử dụng GraalVM installation khác nếu cấu hình không rõ.

Pin wrapper distribution và checksum, plugin version, dependency locks và JDK/GraalVM installation trong CI.

## 10. Kiểm tra Spring Boot plugin và Native Build Tools integration

Nếu dùng Gradle, xác định ai quản lý task nativeCompile và AOT processing: Spring Boot Gradle plugin, Native Build Tools plugin hoặc cấu hình tùy chỉnh. Nếu dùng Maven, kiểm tra Spring Boot Maven Plugin execution và Native Build Tools integration.

Không giả định task/goal giống nhau giữa plugin version. Kiểm tra task list/effective POM và log để biết lifecycle thực tế.

Sau nâng cấp, xác minh:

- AOT processing chạy đúng một lần và dùng đúng profile.
- Native Image nhận đúng build arguments.
- Output executable nằm đúng đường dẫn mà packaging task mong đợi.
- Native tests chạy trên đúng artifact.
- Buildpacks dùng đúng builder/run image.
- Không còn task cũ hoặc plugin duplicate.

## 11. Tạo compatibility matrix cho dự án

Ma trận dự án nên mô tả tổ hợp được CI xác minh. Ví dụ cấu trúc, không phải khuyến nghị version:

| Profile | JDK/GraalVM | Spring Boot | Native Build Tools | Build tool | Target |
|---|---|---|---|---|---|
| Current | Version đã pin | Version đang phát hành | Version đã pin | Wrapper đã pin | linux/amd64 glibc |
| Upgrade candidate | Version đề xuất | Version đích | Version tương thích | Wrapper tương thích | linux/amd64 glibc |
| Secondary target | Cùng release policy | Cùng release policy | Cùng release policy | Cùng wrapper policy | linux/arm64 |

Mỗi hàng cần kết quả build, JVM tests, AOT, native compilation, native tests, container tests và benchmark. Đánh dấu unsupported hoặc not tested rõ ràng; không suy rộng kết quả amd64 sang arm64 hay glibc sang musl.

## 12. Đọc migration guide theo thứ tự nâng cấp

Một thứ tự thực tế giúp giảm số biến thay đổi:

1. Nâng JDK/toolchain tới version được stack hiện tại hỗ trợ.
2. Nâng Gradle/Maven Wrapper nếu version đích yêu cầu.
3. Nâng Spring Boot cùng plugin/BOM tương ứng.
4. Điều chỉnh code theo Spring Framework migration guide.
5. Nâng GraalVM distribution/Native Image.
6. Nâng Native Build Tools theo compatibility matrix.
7. Nâng builder/runtime base image và native packages.
8. Chạy lại toàn bộ pipeline và benchmark.

Thứ tự này có thể thay đổi nếu release notes yêu cầu một tổ hợp cụ thể. Ghi rõ dependency giữa các bước. Không cần nâng tất cả trong một commit nếu có thể tách thành các thay đổi nhỏ dễ review.

## 13. Kiểm tra deprecated API và breaking changes

Tìm các dấu hiệu:

- Compiler deprecation warnings.
- Plugin warnings về task/configuration cũ.
- API Spring bị deprecated/removed.
- Property đổi tên hoặc đổi default.
- Auto-configuration condition thay đổi.
- RuntimeHints API hoặc metadata format thay đổi.
- JDK API bị loại hoặc module không còn có sẵn.
- GraalVM option không còn hỗ trợ.

Bật compiler/plugin warnings trong upgrade branch và lưu log. Không tắt warning hàng loạt để pipeline xanh; phân loại warning mới, warning cũ và warning từ dependency.

Với property migration, kiểm tra effective configuration ở cả JVM và native. Property cũ có thể bị bỏ qua mà không làm build fail.

## 14. Nâng cấp dependency bên thứ ba

Spring Boot BOM không quản lý mọi dependency. Lập inventory các thư viện có tích hợp sâu:

- JDBC drivers và connection pool.
- Jackson/serialization modules.
- Security/OAuth/JWT.
- HTTP clients và TLS providers.
- Messaging clients.
- Logging/metrics/tracing exporters.
- JNI/native libraries.
- SDK cloud/vendor.
- Libraries cung cấp reachability metadata.

Đọc release notes và Native Image support matrix của từng vendor. Kiểm tra thư viện có cung cấp reachability metadata chính thức, có hỗ trợ GraalVM version mới và có thay đổi native binaries theo OS/architecture hay không.

Không nâng dependency chỉ dựa vào version mới. Đánh giá compatibility, security fixes, CVE, license, runtime behavior và khả năng tái hiện build.

## 15. Chạy pipeline xác minh sau nâng cấp

Một upgrade candidate cần đi qua các lớp kiểm tra:

| Stage | Bằng chứng cần có |
|---|---|
| Dependency resolution | Dependency tree/lockfile không có conflict ngoài dự kiến |
| Compile | Main/test sources compile |
| JVM tests | Unit và integration tests pass |
| Spring AOT | AOT processing hoàn tất với profile mục tiêu |
| Native compile | Native Image build thành công |
| Native tests | Test chạy trên native executable hoặc native test runtime |
| Smoke test | Process start, readiness và shutdown đúng |
| Container test | Final image chạy đúng user/base image/architecture |
| Feature tests | JSON, TLS, database, resource, proxy, JNI theo feature |
| Performance | Startup, RSS, throughput/latency so với baseline |

Native compile pass không chứng minh runtime pass. JVM tests pass cũng không chứng minh native reachability đầy đủ. Cần xác minh đúng artifact được đóng gói và triển khai.

## 16. Ví dụ quy trình nâng cấp Spring Boot và GraalVM

Giả sử dự án đang dùng một Spring Boot release line, JDK/GraalVM và Native Build Tools đã pin. Nhóm muốn nâng Spring Boot và GraalVM.

**Trước khi sửa:**

- Ghi version hiện tại từ build manifest.
- Lưu dependency tree, toolchain output và builder digest.
- Chạy pipeline hiện tại để xác nhận baseline.
- Lưu benchmark startup/RSS và test reports.

**Khi nâng:**

- Đọc system requirements và migration guide Spring Boot đích.
- Xác định Spring Framework version đi kèm BOM.
- Đọc GraalVM release notes và Native Image compatibility.
- Kiểm tra Native Build Tools/Gradle compatibility.
- Cập nhật wrapper/plugin/dependency locks.
- Sửa deprecated API, hints và build arguments theo hướng dẫn.

**Sau khi nâng:**

- Chạy JVM/AOT/native/container pipeline.
- Kiểm tra JSON/TLS/resource/profile và thư viện JNI.
- So sánh performance theo cùng protocol.
- Lưu manifest mới và kết quả review.
- Chỉ promote artifact đã được xác minh.

## 17. Khi tài liệu nhà cung cấp mâu thuẫn

Đôi khi một tài liệu nói JDK version được hỗ trợ nhưng plugin hoặc dependency lại yêu cầu version khác. Xử lý theo nguyên tắc:

1. Xác định tài liệu áp dụng cho đúng product/version/distribution.
2. Ưu tiên compatibility matrix/release notes chính thức của component chịu trách nhiệm.
3. Kiểm tra ngày phát hành và tài liệu có được cập nhật cho patch release không.
4. Phân biệt yêu cầu tối thiểu với tổ hợp đã được test.
5. Tạo reproduction nhỏ hoặc compatibility spike trong CI.
6. Ghi rõ tổ hợp được chọn và giới hạn chưa xác minh.
7. Nếu không có tổ hợp giao nhau, chọn version line khác hoặc chờ vendor support.

Không giải quyết mâu thuẫn bằng cách ép version hoặc loại bỏ dependency constraints mà không có test. Một build thành công đơn lẻ không biến tổ hợp đó thành tổ hợp được vendor hỗ trợ.

## 18. Lưu evidence và quyết định nâng cấp

Mỗi upgrade pull request nên có:

- Current/target version table.
- Link/tên release notes và migration guides đã đối chiếu.
- Compatibility matrix của JDK, GraalVM, Spring Boot, plugin và build tool.
- Dependency diff và lockfile changes.
- Native Image arguments changes.
- Test results theo từng stage.
- Container builder/runtime image digest.
- Benchmark trước/sau nếu thay đổi ảnh hưởng performance.
- Known limitations và rollback path.

Không chỉ ghi “đã nâng version”. Reviewer cần biết tại sao tổ hợp mới tương thích và bằng chứng nào chứng minh ứng dụng hoạt động.

## 19. Checklist trước khi chấp nhận upgrade

- Đã đọc Spring Boot system requirements và migration guide đúng version đích.
- Đã xác định Spring Framework version do BOM quản lý.
- Đã đọc Spring Framework What's New/upgrade notes cho API AOT liên quan.
- Đã kiểm tra JDK vendor/version và GraalVM distribution/Native Image compatibility.
- Đã đọc GraalVM release notes về option, target, linker và metadata.
- Đã kiểm tra Native Build Tools plugin compatibility với Gradle/Maven.
- Wrapper và plugin versions được pin.
- Dependency bên thứ ba có native/reachability support được xác minh.
- Buildpacks builder/run image hoặc Docker base image được kiểm tra.
- JVM tests, Spring AOT, Native Image compile và native tests đều có kết quả.
- Final container image được smoke/integration test trên target architecture/libc.
- Performance được so sánh với baseline khi có ảnh hưởng.
- Release evidence và rollback path được ghi lại.

## 20. Câu hỏi tự kiểm tra

1. Vì sao JDK minimum requirement không chứng minh toàn bộ Native Image toolchain tương thích?
2. Spring Boot BOM giúp quản lý Spring Framework version ra sao?
3. Những phần nào trong Spring Framework upgrade guide quan trọng với AOT?
4. Native Build Tools cần tương thích với những thành phần nào?
5. Vì sao phải đọc GraalVM release notes trước khi giữ nguyên build arguments cũ?
6. Khác nhau giữa minimum, supported và tested combination là gì?
7. Vì sao cần test riêng OS/architecture/libc?
8. Khi tài liệu vendor mâu thuẫn, làm thế nào tạo quyết định có bằng chứng?
9. Những stage nào phải chạy sau khi nâng Spring Boot/GraalVM?
10. Upgrade pull request cần lưu evidence gì để reviewer đánh giá?

**Ghi nhớ:** đối chiếu đúng tài liệu và version của từng thành phần, xác định vùng tương thích giao nhau rồi ghi thành compatibility matrix của dự án. Sau nâng cấp, xác minh từ dependency resolution và Spring AOT tới Native Image, native tests và final container trên đúng target trước khi promote.
