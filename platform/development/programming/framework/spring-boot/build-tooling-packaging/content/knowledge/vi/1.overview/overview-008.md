# Trình tự học và tiêu chí kiểm chứng một bản dựng Spring Boot hoàn chỉnh

## 1. Đích đến: thế nào là “bản dựng hoàn chỉnh”?

Trong Spring Boot, **build** là quá trình biến mã nguồn, tài nguyên, cấu hình build và các dependency thành sản phẩm có thể phân phối. Một lệnh báo `BUILD SUCCESS` chỉ chứng minh những tác vụ được lệnh đó thực sự chạy đã hoàn tất; nó **chưa tự chứng minh** gói tạo ra khởi động được, kết nối được môi trường đích hay chứa đúng tài nguyên.

Với một **ứng dụng Spring Boot độc lập** triển khai bằng executable JAR, “hoàn chỉnh” cần có ít nhất bốn lớp bằng chứng:

1. **Đầu vào kiểm soát được:** đúng mã nguồn/commit, JDK, công cụ build, plugin và dependency đã xác định.
2. **Build và test đạt:** biên dịch, xử lý resource, kiểm tra tự động được cấu hình và package không lỗi; không âm thầm bỏ qua test.
3. **Artifact đúng loại:** tạo được executable JAR với lớp ứng dụng và dependency cần thiết; có thể chạy bằng `java -jar` trong điều kiện phù hợp.
4. **Chạy và bàn giao kiểm chứng được:** app khởi động với cấu hình dự kiến, hoàn thành một phép thử hành vi, có thông tin phiên bản và đầu ra CI có thể truy vết.

Nếu dự án chọn **WAR** để triển khai lên servlet container hoặc **OCI image** để chạy trong container, thay tiêu chí JAR bằng tiêu chí của loại artifact đó và thêm phép thử trên đúng môi trường triển khai. Không yêu cầu tạo mọi loại artifact cho cùng một bài tập.

Luồng tư duy cần nắm:

~~~text
Source + build definition + lock/toolchain
    -> resolve dependencies
    -> compile + process resources
    -> execute quality gates/tests
    -> package executable archive
    -> inspect archive
    -> run packaged artifact
    -> smoke test + publish evidence
~~~

**Nguyên tắc xuyên suốt:** kiểm chứng *artifact vừa được đóng gói*, không chỉ chạy ứng dụng từ IDE hay từ `bootRun` / `spring-boot:run`. Cách chạy phát triển dùng classpath do công cụ build dựng nên, nên có thể che giấu lỗi đóng gói.

## 2. Trình tự học đề xuất: học theo phụ thuộc và đầu ra quan sát được

| Chặng | Cần hiểu và thực hành | Bằng chứng đạt trước khi sang chặng kế |
| --- | --- | --- |
| 1. Toolchain & cấu trúc | Xác định JDK, Maven/Gradle Wrapper, `pom.xml` hoặc `build.gradle(.kts)`, mã nguồn `src/main` và test `src/test`. | Ghi được phiên bản Java/build tool và chạy được lệnh kiểm tra phiên bản từ Wrapper. |
| 2. Dependency & plugin | Phân biệt Spring Boot plugin, starter, BOM/dependency management, repository và dependency scope/configuration. | Giải thích được thư viện nào cần khi biên dịch, test và chạy; không có dependency không giải quyết được. |
| 3. Biên dịch & resource | Hiểu `compile`, resource processing, cấu hình, main class, source set/module. | Mã biên dịch thành công và resource mong đợi có mặt trong đầu ra. |
| 4. Kiểm thử & quality gate | Chạy unit test, integration test (nếu có), kiểm tra cấu hình và mã nguồn; đọc report. | Test thực sự được phát hiện và chạy; report thể hiện số test, fail/skip rõ ràng. |
| 5. Đóng gói | Phân biệt JAR thư viện, executable Spring Boot JAR, WAR, OCI image; hiểu `repackage` / `bootJar`. | Artifact ở đúng thư mục, đúng dạng và có dấu hiệu chứa dependency/runtime launcher. |
| 6. Kiểm chứng runtime | Chạy bản đóng gói bằng Java phù hợp, truyền cấu hình ngoài, quan sát log và thử một use case. | Startup thành công, endpoint/job thực hiện đúng, shutdown được; các dependency môi trường đã sẵn sàng. |
| 7. Phát hành & CI | Build từ commit sạch, lưu test report, checksum, artifact và thông tin build; thử trên runner sạch. | Pipeline có thể tạo lại kết quả, artifact bàn giao được nhận diện và kiểm thử như chính bản sẽ triển khai. |
| 8. Chẩn đoán | Cố ý tạo lỗi dependency, test, packaging, port/config rồi tìm bằng chứng. | Chỉ ra được lỗi phát sinh ở chặng nào, cách khắc phục và lệnh xác minh lại. |

Học theo thứ tự này vì mỗi chặng tiêu thụ đầu ra của chặng trước: runtime không thể chứng minh đúng khi chưa chắc artifact đúng; artifact không nên được phát hành khi test hoặc dependency chưa tin cậy. Ở cấp “Tổng quan”, mục tiêu là đọc và đánh giá một pipeline build từ đầu đến cuối, chưa cần tối ưu mọi plugin nâng cao.

## 3. Chặng 1–2: khóa đầu vào và hiểu quy tắc dependency

### 3.1. Nhận diện dự án

- **Maven:** `pom.xml`, Maven Wrapper (`mvnw` / `mvnw.cmd`); lifecycle gồm các phase như `compile`, `test`, `package`, `verify`. Các goal được plugin gắn vào phase quyết định việc gì chạy thật.
- **Gradle:** `settings.gradle(.kts)`, `build.gradle(.kts)`, Gradle Wrapper (`gradlew` / `gradlew.bat`); các task thường gặp: `compileJava`, `processResources`, `test`, `bootJar`, `build`. Quan hệ phụ thuộc task quyết định trình tự.
- **JDK:** phiên bản dùng để build phải phù hợp phiên bản Spring Boot, plugin và bytecode mục tiêu; runtime triển khai cũng phải hỗ trợ bytecode đó. Kiểm tra cả `java` lẫn `javac`, không dựa vào JDK đang chọn trong IDE.
- **Wrapper:** lưu và sử dụng Wrapper trong repository để nhóm/CI cùng chọn một phiên bản Maven hoặc Gradle đã quy định. Wrapper **không tự cố định JDK**; cần thêm toolchain hoặc cấu hình runner tương ứng.

~~~bash
# macOS/Linux: chọn bộ lệnh phù hợp dự án
java -version
javac -version
./mvnw -version
# Hoặc dự án Gradle:
./gradlew --version
~~~

Trên Windows, dùng `mvnw.cmd -version` hoặc `gradlew.bat --version`. Không bắt buộc một dự án phải có cả Maven và Gradle.

### 3.2. Đọc bản đồ dependency trước khi build

Spring Boot starter gom những thư viện phổ biến; dependency management/BOM điều phối phiên bản tương thích nhưng không tự bổ sung mọi thư viện vào ứng dụng. Cần phân biệt:

- Maven `compile`/`runtime`/`test`/`provided` và Gradle `implementation`/`runtimeOnly`/`testImplementation`/`compileOnly`: chúng ảnh hưởng classpath và nội dung package theo cách khác nhau; **không coi các scope/configuration là tương đương tuyệt đối**.
- Thư viện chỉ dùng trong test không nên nằm trong artifact production. Thư viện cần khi chạy phải có mặt trong classpath runtime, trừ khi môi trường triển khai chủ động cung cấp nó.
- Plugin build có vai trò khác dependency ứng dụng: khai báo Spring Boot Maven/Gradle plugin để có thao tác đóng gói executable; khai báo web starter để app có HTTP server; một thứ không thay thế thứ kia.

Lệnh điều tra khi version conflict hoặc thiếu dependency:

~~~bash
# Maven: xem cây dependency đã giải quyết
./mvnw dependency:tree

# Gradle: xem cấu hình runtime của dự án Java
./gradlew dependencies --configuration runtimeClasspath
~~~

Các lệnh trên yêu cầu plugin/cấu hình tương ứng tồn tại. Với Gradle multi-project, chỉ định task của đúng module khi cần; với Maven multi-module, chọn module ứng dụng theo reactor. Đạt chặng này khi giải thích được **vì sao** một thư viện vào hoặc không vào runtime archive và có thể nhận ra xung đột phiên bản.

## 4. Chặng 3–4: biên dịch, resource và test có bằng chứng

### 4.1. Biên dịch thành công chưa đủ

Biên dịch kiểm tra tính hợp lệ của mã Java và tạo class; xử lý resource sao chép/có thể biến đổi file cấu hình, template, static asset. Với ứng dụng nhiều module cần kiểm tra module có `@SpringBootApplication` và main method được chọn là module đóng gói, thay vì đóng gói nhầm library.

Một checklist tối thiểu:

- Không có lỗi compiler; dùng đúng source/target/toolchain.
- Có tài nguyên cần thiết từ `src/main/resources` (ví dụ file YAML, template hoặc static file thực sự dùng).
- Không đưa credential, key bí mật hay cấu hình chỉ hợp lệ trên máy lập trình vào artifact.
- Không đánh giá việc build qua việc IDE hiển thị màu xanh; chạy lại bằng Wrapper ở terminal.

### 4.2. Hiểu test nào đang chạy

| Kiểm thử | Nó chứng minh điều gì? | Giới hạn |
| --- | --- | --- |
| Unit test | Logic cô lập cho kết quả mong đợi. | Không chứng minh app khởi động hay kết nối hạ tầng. |
| Integration test | Các thành phần như Spring context, DB, queue, HTTP client phối hợp theo hợp đồng. | Chỉ đúng với môi trường, fixture và tuyến kiểm thử đã cấu hình. |
| Smoke test trên artifact | Gói đã tạo khởi động và làm được hành vi cốt lõi. | Không thay thế test logic, bảo mật, tải hay kiểm tra sản xuất. |

~~~bash
# Maven: chạy các phase đến verify, gồm test mặc định và
# integration-test/verify bổ sung nếu dự án cấu hình plugin tương ứng
./mvnw clean verify

# Gradle với Java/Spring Boot plugin: chạy assemble + check theo task graph
./gradlew clean build
~~~

**Quan sát bằng chứng:** mã thoát lệnh bằng 0, dòng tổng kết test/report, tên suite đã chạy, số test thực thi, số lỗi và skipped. Maven Surefire thường báo cáo tại `target/surefire-reports/`; Failsafe nếu được cấu hình có report riêng; Gradle Java test thường tại `build/test-results/test/` và `build/reports/tests/test/`. Vị trí có thể đổi khi build script tùy biến.

Lưu ý phân biệt: `verify` của Maven **không tự động bảo đảm có integration test** nếu dự án chưa gắn Failsafe hoặc plugin tương đương; Gradle `build` cũng **không tự tạo một task integrationTest**. Thao tác bỏ test (ví dụ `-DskipTests`, `-Dmaven.test.skip=true`, `-x test`) chỉ dùng khi có lý do được duyệt; không xem bản dựng như đã qua test gate.

## 5. Chặng 5: đóng gói đúng artifact sẽ phát hành

### 5.1. Ba kết quả phổ biến

| Đầu ra | Công dụng | Cách nhận biết/thử |
| --- | --- | --- |
| **Executable JAR** | Chạy ứng dụng Spring Boot độc lập bằng `java -jar`. | JAR chứa launcher/manifest thích hợp, class ứng dụng và runtime dependency; chạy được. |
| **WAR** | Chạy bằng `java -jar` khi được đóng gói executable, hoặc triển khai lên external servlet container khi cấu hình phù hợp. | Kiểm tra cấu trúc `WEB-INF` và thử đúng kiểu vận hành mục tiêu. |
| **OCI image** | Phân phối ứng dụng kèm runtime/base image cho container platform. | Build ra image tag/digest và chạy thử container với config/port phù hợp. |

Spring Boot executable JAR thường có class ứng dụng trong `BOOT-INF/classes`, dependency trong `BOOT-INF/lib` và manifest dùng launcher phù hợp. Một JAR Java thông thường có thể biên dịch và package thành công nhưng **không** chạy được bằng `java -jar` với toàn bộ dependency của ứng dụng Spring Boot.

### 5.2. Lệnh gắn với Maven/Gradle

- **Maven:** với `spring-boot-maven-plugin` và execution `repackage` được cấu hình, lifecycle `package`/`verify` có thể tạo executable archive. Dự án dùng `spring-boot-starter-parent` thường đã có execution `repackage`, nhưng vẫn cần khai báo plugin; nếu không dùng parent phải tự cấu hình execution tương ứng. `mvn package spring-boot:repackage` là cách gọi tường minh khi cần.
- **Gradle:** dự án áp dụng Spring Boot plugin cùng Java plugin có task `bootJar`; `bootWar` áp dụng khi có War plugin phù hợp. Task `jar` thông thường không đồng nghĩa `bootJar`; xem task graph thực tế của dự án.
- **OCI:** tùy cấu hình có `./gradlew bootBuildImage` hoặc `./mvnw spring-boot:build-image`; Spring Boot Buildpacks cần truy cập container daemon tương thích, thường là Docker. Việc build được image không bảo đảm service bên trong healthy khi chạy.

~~~bash
# Nếu bài tập dùng Maven, đầu ra thường ở target/
./mvnw clean verify

# Nếu bài tập dùng Gradle, đầu ra thường ở build/libs/
./gradlew clean build

# Kiểm tra nội dung JAR thực tế, thay đường dẫn theo file vừa tạo
jar tf target/demo-0.0.1-SNAPSHOT.jar
~~~

Ví dụ dòng `jar tf` ở trên chỉ dành cho **artifact mẫu Maven có đúng tên đó**. Với Gradle dùng đường dẫn JAR trong `build/libs/`. Trong listing của executable JAR, tìm `BOOT-INF/classes/`, `BOOT-INF/lib/` và `META-INF/MANIFEST.MF`; thông tin manifest và launcher có thể khác theo thế hệ Spring Boot. Cấu trúc archive chỉ là kiểm tra *tĩnh*; bước tiếp theo bắt buộc chạy thật.

## 6. Chặng 6: bài thực hành xuyên suốt từ source đến runtime

**Bài tập:** dùng một dự án Spring Boot Web với starter web thích hợp phiên bản đang sử dụng, một JDK tương thích, Spring Boot build plugin và một endpoint nhỏ. Dùng file `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Đây là **class Java đầy đủ**, nhưng để chạy được phải đặt trong **dự án Spring Boot đã cấu hình** các dependency và plugin cần thiết. `@SpringBootApplication` thiết lập ứng dụng và auto-configuration; `@RestController` công bố handler; `@GetMapping("/ping")` ánh xạ HTTP GET tới chuỗi `pong`. Không cần suy đoán phiên bản dependency: dùng bộ version phù hợp do dự án quản lý.

Tiến hành theo chuỗi kiểm chứng sau:

1. **Chuẩn bị:** ghi commit/revision, phiên bản JDK, Wrapper; đảm bảo endpoint có thể biên dịch và ít nhất một test tự động có ý nghĩa (ví dụ test logic hoặc kiểm tra HTTP/status phù hợp phiên bản framework).
2. **Build:** chọn **một** bộ lệnh `./mvnw clean verify` hoặc `./gradlew clean build`, xác nhận các test mong đợi đã chạy. Chưa đạt thì dừng, không chuyển qua phát hành.
3. **Xác nhận artifact:** liệt kê file JAR thật; dùng `jar tf` và kiểm tra nó là executable Boot archive. Với dự án nhiều module, chọn đúng archive của module ứng dụng.
4. **Chạy bằng artifact:** mở terminal mới rồi chạy một trong các lệnh dưới, thay tên file đúng với sản phẩm đã build và chỉ dùng một instance.
5. **Smoke test:** tại terminal khác gửi HTTP GET và kiểm tra **status 200**, response body **chính xác `pong`**, app vẫn ổn định trong thời gian thử.
6. **Shutdown:** dừng process bằng Ctrl+C, xác nhận không còn chạy ở cổng thử và lưu log/lệnh build/test trong biên bản.

~~~bash
# Ví dụ với Maven và tên artifact minh họa:
java -jar target/demo-0.0.1-SNAPSHOT.jar --server.port=8085

# Hoặc với Gradle và tên artifact minh họa:
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar --server.port=8085
~~~

~~~bash
# Gọi sau khi application log xác nhận đã khởi động
curl -i http://localhost:8085/ping
~~~

Kỳ vọng: HTTP `200 OK` và **response body là `pong`**. Header, log startup, thời gian, PID, biểu diễn status line và cổng mặc định phụ thuộc runtime nên **không** coi log mẫu cố định là điều kiện pass. Nếu `curl` không khả dụng, dùng HTTP client tương đương; chứng cứ cần có request, status và body. Với Spring Batch/CLI không có HTTP endpoint, thay phép thử trên bằng **một job/input tối thiểu** có kết quả xác minh được, mã thoát và output hợp đồng.

**Thử một thay đổi cấu hình có chủ đích:** đổi cổng sang 8085 bằng tham số runtime như trên, không sửa source và không build lại. Việc app lắng nghe ở 8085 minh họa *externalized configuration*. Profile, URL database và secret nên được cung cấp bởi môi trường chạy theo cơ chế phù hợp, không nhúng vào JAR. Nếu có dependency ngoài (DB, broker), ghi rõ điều kiện cần để khởi động; “chạy được trên máy tôi” chưa phải là chứng cứ triển khai tái lập.

## 7. Chặng 7: cổng chất lượng và tiêu chí chấp nhận cuối cùng

Đánh giá bằng **bằng chứng quan sát được**, tránh kết luận chỉ từ một dòng log hoặc kích thước JAR.

| Cổng | Tiêu chí PASS | Bằng chứng giữ lại |
| --- | --- | --- |
| **G1 — Input** | Xác định commit, Java, Wrapper, plugin/build config và nguồn dependency; không dựa vào thiết lập IDE ngầm. | Commit SHA, output `--version`, build definition/lockfile nếu dự án sử dụng. |
| **G2 — Compile/resources** | Biên dịch và đóng gói resource cần dùng không lỗi. | Kết quả task/phase, file/tài nguyên trong artifact. |
| **G3 — Tests** | Các test được quy định đã chạy và đạt; mọi skip có lý do được phê duyệt. | Exit code, report, số test/pass/fail/skip, danh sách suite. |
| **G4 — Package** | Có đúng định dạng cần triển khai, manifest/launcher/runtime dependency phù hợp. | Đường dẫn artifact, `jar tf`/manifest hoặc metadata image/WAR. |
| **G5 — Runtime** | Chạy **artifact phát hành**, khởi động không lỗi, cấu hình ngoài được áp dụng, hành vi cốt lõi đúng. | Lệnh `java -jar` / container, startup log, HTTP/job smoke result, exit/shutdown. |
| **G6 — Reproduce & handoff** | Pipeline độc lập tạo và lưu artifact có định danh phiên bản; đội triển khai biết lấy bản nào. | CI job run, commit, artifact name/version, checksum/digest, test report. |
| **G7 — Gate riêng của đích** | Nếu WAR/container/native packaging được chọn, phép thử của loại đó đạt. | Container health/probe, servlet deploy smoke hoặc tiêu chí chuyên biệt tương ứng. |

**Định nghĩa hoàn tất cho bài tập:** các cổng G1–G6 đều PASS; G7 chỉ áp dụng nếu phạm vi triển khai yêu cầu. Chữ “PASS” phải dẫn tới chứng cứ có thể kiểm lại. Nếu chưa có CI, ghi trạng thái G6 là **chưa đạt** thay vì giả định lệnh local tương đương pipeline sạch. Nếu đây mới là bài thực hành học tập, có thể hoàn thành mốc local ở G1–G5 và ghi G6 thành mục tiêu của chặng tiếp theo, nhưng chưa gọi đó là bản dựng sẵn sàng bàn giao.

Một bản ghi bàn giao ngắn gọn có thể theo mẫu:

~~~text
Commit: <ma-commit>
Build tool: <maven-hoac-gradle-wrapper> / version
JDK build + runtime: <version>
Build command: <command>
Tests: <so-chay> executed, 0 failures, <so-skip> skipped (ly do neu co)
Artifact: <duong-dan-va-ten-file>
SHA-256 / image digest: <gia-tri-do-tu-artifact-thuc-te>
Run command / environment: <lenh-va-config-khong-chua-secret>
Smoke test: <input> -> <status/ket-qua>
CI run / artifact location: <tham-chieu-neu-co>
Result: PASS hoac FAIL kem gate va bang-chung
~~~

Các dòng trong block trên là **mẫu điền thông tin**, không phải log đã đo được. Với checksum, tính trực tiếp trên artifact thực sự phân phối: Linux thường dùng `sha256sum`, Windows PowerShell dùng `Get-FileHash -Algorithm SHA256`; image cần lưu digest nếu việc phân phối dựa vào registry.

## 8. Khả năng tái lập, độ tin cậy và ranh giới với “production ready”

Một build có thể chạy được một lần nhưng vẫn không đáng tin nếu cần state ẩn. Tập trung các điểm sau khi chuyển từ local sang CI:

- **Dùng toolchain rõ ràng:** Wrapper và JDK mục tiêu cố định theo project; tránh “máy A dùng Java 17, máy B dùng Java 23” mà không kiểm tra tương thích.
- **Ổn định phiên bản:** dùng dependency management/lock hoặc chính sách version được duyệt; tránh selector động hoặc snapshot không kiểm soát trong bản phát hành. Nếu repository remote thay đổi, cần lưu thông tin nguồn và checksum khi có yêu cầu.
- **Không lệ thuộc local cache:** thử build trên runner/workspace sạch; cache tăng tốc nhưng không được làm thay đổi đầu ra đúng đắn.
- **Bảo toàn artifact:** build một lần ở CI, kiểm thử đúng artifact đó rồi phân phối cùng bản, tránh rebuild riêng ở bước deploy khiến binary khác. Gắn commit, version và checksum/digest để truy vết.
- **Bảo mật đầu ra:** quét dependency và image khi quy trình yêu cầu; không đóng gói secret hay file chỉ dành cho development; cập nhật base image khi chọn OCI. SBOM, chữ ký artifact, provenance, license scan là các gate tùy mức độ bảo đảm của dự án.
- **Bất biến cấu hình theo môi trường:** artifact giữ nguyên khi chuyển dev/test/prod; thông số môi trường được cấp ngoài và kiểm tra bằng smoke test ở môi trường mục tiêu.

**Phân biệt ba mức độ:** `compiles` = biên dịch thành công; `build verified` = test + package + chạy artifact theo tiêu chí đã công bố; `production ready` còn đòi hỏi vận hành, bảo mật, quan sát, phục hồi, hiệu năng, rollout/rollback, hạ tầng và phê duyệt tùy hệ thống. Không đánh đồng ba mức này.

## 9. Lỗi phổ biến: tìm đúng chặng thay vì chạy lại vô hướng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Chạy được trong IDE, `java -jar` báo `no main manifest attribute`. | Tạo plain JAR, thiếu/skip Boot repackage hoặc chọn nhầm file. | Xem plugin/task, manifest và cấu trúc archive; chọn executable JAR rồi build lại. |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` khi startup. | Dependency chỉ có ở compile/test, bị exclude hoặc classpath runtime không đúng. | Xem dependency tree/runtimeClasspath, đối chiếu `BOOT-INF/lib` và scope. |
| `UnsupportedClassVersionError`. | JDK dùng chạy quá cũ so với bytecode đã build. | Kiểm tra `java -version` ở runtime và cấu hình toolchain/target. |
| Build xanh nhưng số test bằng 0 hoặc test quan trọng bị bỏ qua. | Không phát hiện test, filter sai, skip flag, thiếu task/goal integration test. | Đọc report/task graph, cấu hình JUnit/Surefire/Failsafe hoặc Gradle test task đúng. |
| JAR có đủ class nhưng thiếu `application.yml`/template. | Resource processing/source set hoặc vị trí file sai. | Kiểm tra resource nguồn, cấu hình build và `jar tf`. |
| Startup lỗi port hoặc DB/secret. | Port bị dùng, profile sai, dependency ngoài chưa sẵn sàng. | Đọc **nguyên nhân đầu tiên** trong stack trace, kiểm tra port, profile, biến môi trường và dịch vụ phụ thuộc. |
| Local pass, CI fail. | Khác JDK, môi trường, đường dẫn, quyền, timezone, locale, cache hoặc test phụ thuộc thứ tự. | So sánh toolchain/environment được ghi lại; chạy lại bằng Wrapper trên môi trường sạch. |
| Đã build image nhưng container không healthy. | Sai port/exposed port, startup command, config hoặc readiness dependency. | Chạy image cụ thể, xem logs, kiểm tra health endpoint/probe và mapping port. |

Hãy sửa **nguyên nhân** tại chặng tương ứng rồi chạy lại từ gate bị ảnh hưởng đến hết chuỗi: sửa dependency cần rebuild + test + package + runtime smoke; sửa config runtime vẫn phải thử artifact trong môi trường định triển khai.

## 10. Tự đánh giá sau khi học

Bạn đạt mục tiêu của bài khi có thể tự trả lời và chứng minh được:

1. Dự án dùng Wrapper nào, JDK nào, phiên bản plugin/dependency được quản lý ở đâu?
2. Vì sao `./mvnw clean verify` và `./gradlew clean build` không bảo đảm integration test tồn tại nếu không cấu hình?
3. Khác biệt giữa `jar` Java thông thường và `bootJar` / Spring Boot Maven `repackage` là gì?
4. Artifact phát hành nằm ở đâu; bạn đã kiểm tra nội dung và **chạy chính artifact đó** hay mới chạy từ IDE?
5. Test nào chứng minh logic, test nào chứng minh tích hợp, phép thử nào chứng minh packaged runtime?
6. Nếu startup fail, bạn có phân biệt lỗi thiếu dependency, sai JDK, port, cấu hình ngoài và service phụ thuộc không?
7. Một người khác có thể truy vết cùng commit, build tool, kết quả test và artifact checksum/digest để xác minh lại không?
8. Với target là WAR hoặc OCI, bạn có thay tiêu chí chấp nhận cho đúng môi trường chạy không?

**Bài tập kết thúc:** nộp một biểu mẫu G1–G7 cùng bằng chứng thực tế, chỉ rõ PASS/FAIL cho từng cổng, tối thiểu có một log build, test report, đường dẫn artifact, kết quả kiểm tra archive, lệnh chạy và smoke test. Nếu có FAIL, giải thích lỗi nằm ở chặng nào và điều kiện nào cần thay đổi để chuyển sang PASS.

## Tài liệu tham khảo chính thức

- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Spring Boot Maven Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)

Các lệnh minh họa giả định module ứng dụng đã cấu hình đúng Spring Boot plugin, starter và phiên bản Java phù hợp. Hãy dựa vào build definition của dự án thật để chọn lệnh và file artifact chính xác.