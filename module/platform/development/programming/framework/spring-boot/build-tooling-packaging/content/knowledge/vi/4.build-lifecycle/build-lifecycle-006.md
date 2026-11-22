# Phân biệt clean, build tăng dần và chạy lại tác vụ trong dự án Spring Boot

## 1. Ba thao tác giải quyết ba nhu cầu khác nhau

Khi phát triển Spring Boot với Maven hoặc Gradle, cùng một dự án có thể được build liên tiếp nhiều lần. Điều cần phân biệt là: **xóa trạng thái đầu ra cũ**, **tận dụng kết quả vẫn còn hợp lệ**, và **yêu cầu thực thi lại công việc dù đầu vào không đổi**.

| Khái niệm | Mục đích chính | Có xóa đầu ra build? | Có bắt buộc thực thi lại mọi công việc? |
|---|---|---|---|
| **Clean** | Xóa file đã sinh để bắt đầu với thư mục output sạch | Thông thường có: Maven xóa `target/`; Gradle xóa `build/` | Không tự build lại; nếu kết hợp build, có thể vẫn tận dụng cache ngoài thư mục output |
| **Build tăng dần (incremental)** | Tránh tính lại phần kết quả không bị ảnh hưởng bởi thay đổi | Không, nếu không gọi clean | Không; chỉ công việc cần thiết mới được thực thi lại |
| **Chạy lại tác vụ (rerun)** | Buộc một tác vụ hay các tác vụ được chọn thực thi lại | Không nhất thiết | Có, trong phạm vi lệnh/cơ chế rerun; vẫn tồn tại điều kiện bỏ qua theo đặc tính task |

Hai cách dùng từ cần phân biệt:

- **Build tăng dần ở cấp tác vụ**: công cụ thấy đầu vào/đầu ra của một task vẫn hợp lệ nên **không chạy** task đó.
- **Xử lý tăng dần bên trong một tác vụ**: task vẫn được chạy, nhưng trình biên dịch hoặc plugin chỉ xử lý phần thay đổi. Ví dụ `compileJava` chạy, nhưng incremental Java compilation có thể chỉ biên dịch một phần source cùng các file bị ảnh hưởng.

Không có một lệnh `build` thống nhất cho mọi công cụ. Maven sử dụng các **lifecycle phase/goal**; Gradle sử dụng **task graph**. Vì thế cùng khái niệm nhưng cách điều khiển và trạng thái hiển thị khác nhau.

## 2. Hiểu clean: xóa kết quả, không xóa mã nguồn

### Maven

Với project Spring Boot dùng Maven, các lệnh thường dùng là:

```bash
# Chỉ xóa đầu ra của quá trình build
./mvnw clean

# Build theo lifecycle mặc định đến phase package
./mvnw package

# Xóa output cũ, rồi thực hiện các phase đến package
./mvnw clean package
```

Trên Windows, dùng `mvnw.cmd` thay cho `./mvnw`.

`clean` là phase thuộc **clean lifecycle** riêng biệt. Theo thiết lập thông thường, Maven Clean Plugin xóa thư mục `target/`, gồm `target/classes`, kết quả test và JAR/WAR đã đóng gói. `package` thuộc **default lifecycle**, nên Maven đi qua các phase cần thiết trước `package` theo thứ tự, gồm biên dịch mã nguồn, biên dịch test, chạy test và đóng gói, tùy `packaging` và các plugin.

`./mvnw clean` **không** đồng nghĩa `./mvnw clean package`: lệnh thứ nhất chỉ thực hiện clean, không tạo lại JAR. `clean` cũng **không xóa** thư viện tải xuống trong cache Maven của người dùng (thường ở `~/.m2/repository`). Nếu dự án cấu hình output khác mặc định, phạm vi clean có thể được điều chỉnh bởi plugin.

### Gradle

Với project Spring Boot dùng Gradle:

```bash
# Chỉ xóa build directory
./gradlew clean

# Thực thi các tác vụ mà lifecycle task build phụ thuộc vào
./gradlew build

# Xóa build directory trước, sau đó build
./gradlew clean build
```

Trên Windows, dùng `gradlew.bat` thay cho `./gradlew`.

`clean` thông thường là task kiểu `Delete` xóa `build/` của project được áp dụng. `build` thường phụ thuộc vào nhóm task tạo artifact (`assemble`) và nhóm kiểm tra (`check`), theo các plugin được áp dụng. Với Spring Boot, task `bootJar` hoặc `bootWar` do plugin Spring Boot cung cấp sẽ tham gia vào quy trình đóng gói tùy cấu hình project. Không nên suy luận rằng mọi project đều tạo cùng tập artifact.

**Điểm quan trọng:** `clean` xóa output trong thư mục build, nhưng **không nhất thiết xóa Gradle build cache**. Nếu build cache đang bật và task đủ điều kiện, sau `clean` Gradle vẫn có thể khôi phục output từ cache với trạng thái `FROM-CACHE`. Vì vậy “clean rồi build” không luôn tương đương “tự thực thi lại từng task từ đầu”.

Cả Maven và Gradle đều không yêu cầu `clean` mỗi lần sửa một file. Clean thường làm build chậm hơn khi không cần thiết.

## 3. Build tăng dần trong Gradle hoạt động thế nào?

Gradle mô hình hóa build dưới dạng đồ thị task và quan hệ phụ thuộc. Một task điển hình có:

- **Inputs**: source Java, classpath, property, cấu hình ảnh hưởng đến output.
- **Outputs**: file `.class`, JAR, file resources được copy hoặc tài liệu tạo ra.
- **Task implementation**: cách task biến input thành output.

Ở những task có theo dõi trạng thái phù hợp, Gradle ghi nhận dấu vết của input và output từ lần thực thi trước. Khi chạy lại, Gradle so sánh trạng thái đã ghi với trạng thái hiện tại:

```text
Yêu cầu: ./gradlew build
             |
             v
      Xây task graph
             |
             v
  Task có điều kiện thực thi?
        /         \
      Không        Có
       |            |
  SKIPPED/...   Input và output vẫn hợp lệ?
                  /             \
                 Có             Không
                  |                |
              UP-TO-DATE     Cache có output hợp lệ?
                                /          \
                               Có          Không
                                |             |
                            FROM-CACHE    Thực thi task
                                         (có thể tăng dần
                                          bên trong task)
```

Sơ đồ mang tính khái niệm: Gradle còn nhiều điều kiện như `NO-SOURCE`, các task không theo dõi trạng thái, cấu hình cache, kiểm tra output và điều kiện của plugin. Không phải task nào cũng được cache hoặc tối ưu giống nhau.

Ví dụ chạy hai lần liên tiếp, **không sửa file**:

```bash
./gradlew build --console=plain
./gradlew build --console=plain
```

Ở lần thứ hai, nhiều task đủ điều kiện có thể được in là `UP-TO-DATE`. Những task không có action hoặc không có output có thể có cách hiển thị khác. Đừng coi mọi task bắt buộc phải hiển thị `UP-TO-DATE` mới là build đúng.

### Đọc trạng thái task Gradle

| Trạng thái | Diễn giải | Có thực thi lại action của task? |
|---|---|---|
| `UP-TO-DATE` | Input/output chưa đổi so với trạng thái được ghi nhận | Không |
| `FROM-CACHE` | Output được khôi phục từ build cache hợp lệ | Không |
| `NO-SOURCE` | Task nguồn không có source cần xử lý | Không |
| `SKIPPED` | Task bị bỏ qua theo điều kiện hoặc cấu hình | Không |
| Không có nhãn kết quả bỏ qua | Task có thể đã thực thi bình thường | Có, tùy loại task |
| `FAILED` | Task thực thi nhưng gặp lỗi | Không thành công |

**Incremental build** và **build cache** không đồng nhất:

- `UP-TO-DATE` thường có nghĩa output hiện tại ở máy đã hợp lệ, không cần chạy lại.
- `FROM-CACHE` nghĩa output hiện tại được lấy từ bản lưu có cùng input/implementation phù hợp, kể cả khi output trước đó đã bị xóa.
- `--build-cache` hoặc `org.gradle.caching=true` có thể được dùng để bật build cache tùy cấu hình. Một task chỉ được cache khi đủ điều kiện; có bật cache không có nghĩa mọi task sẽ `FROM-CACHE`.
- **Configuration cache** là tối ưu khác: lưu kết quả giai đoạn cấu hình task graph, không phải chính các output của `compileJava` hoặc `test`. Nó không thay thế việc kiểm tra tính hợp lệ của output.

Còn một tầng tối ưu nữa: **incremental compilation**. Khi sửa một Java class, `compileJava` có thể chạy lại nhưng chỉ biên dịch các source bị ảnh hưởng; các thay đổi làm ảnh hưởng rộng đến API/classpath có thể khiến phần mã lớn hơn cần được biên dịch.

## 4. Maven có build tăng dần giống Gradle không?

Maven tổ chức công việc theo ba lifecycle chính: `default`, `clean` và `site`. Phase không phải task Gradle. Khi gọi:

```bash
./mvnw package
```

Maven kích hoạt các **plugin goal** ràng buộc với các phase từ đầu đến `package`. Một số plugin, như Maven Compiler Plugin, có cơ chế tránh biên dịch lại khi không cần hoặc xử lý theo thay đổi nguồn và output, tùy phiên bản và cấu hình. Một số goal khác vẫn được gọi và tự quyết định có công việc gì cần làm.

Vì vậy:

- `./mvnw package` lần hai có thể nhanh hơn lần đầu do output còn đó, dependency đã tải và plugin có tối ưu.
- **Maven core không cung cấp cùng mô hình nhãn `UP-TO-DATE` / `FROM-CACHE` cho mọi goal như Gradle.** Đừng kết luận “không tăng dần” chỉ vì log Maven khác log Gradle.
- Không thể dùng chung cờ Gradle `--rerun-tasks` cho Maven; đây không phải option Maven.
- Khi cần đối chiếu hành vi, xem chính plugin nào được gọi, phiên bản plugin, các thông báo “Nothing to compile”, các báo cáo test và trạng thái đầu ra.

Trong project Spring Boot Maven, Maven plugin để đóng gói executable JAR (ví dụ `spring-boot-maven-plugin` với goal `repackage` khi được cấu hình) là một bước khác với Java compiler; tránh đánh đồng “không biên dịch lại class” với “không thực hiện đóng gói JAR”.

## 5. Chạy lại tác vụ: không nhất thiết phải clean

### Gradle: `--rerun-tasks`

Giả sử muốn thực thi lại các task cần thiết cho test, dù Gradle đang cho rằng output hợp lệ:

```bash
./gradlew test --rerun-tasks --console=plain
```

Theo cách hoạt động của Gradle, `--rerun-tasks` yêu cầu chạy lại các task trong task graph được chọn (gồm task phụ thuộc), bỏ qua kiểm tra up-to-date thường dùng; **không xóa toàn bộ `build/` trước khi chạy**. Vì cờ tác động lên đồ thị task, nó có thể khiến `compileJava`, `compileTestJava` và những task liên quan thực thi lại, chứ không chỉ riêng `test`.

Vẫn cần hiểu giới hạn: task `NO-SOURCE`, task bị disable hoặc điều kiện skip có thể không thực thi action bình thường. Cờ cũng không tự sửa sai dependency, tải lại tất cả dependency hay chứng minh rằng code sản phẩm đúng.

Muốn chạy lại việc đóng gói:

```bash
./gradlew bootJar --rerun-tasks --console=plain
```

Lệnh trên phù hợp khi project đã áp dụng plugin Spring Boot tạo task `bootJar`; trong dự án khác, hãy chọn task tương ứng (`jar`, `bootWar` hoặc task của module). Để chọn test cụ thể trong một dự án dùng task test/JUnit phù hợp:

```bash
./gradlew test --tests "com.example.demo.OrderServiceTest" --rerun-tasks
```

Tên test ở đây là **ví dụ**; chỉ chạy được khi class đó tồn tại và công cụ test đã được cấu hình.

### Maven: gọi lại phase/goal hoặc clean khi cần xây dựng lại từ output mới

Maven không có cờ `--rerun-tasks` tương đương. Để kích hoạt lại lifecycle đến phase `test`:

```bash
./mvnw test
```

Để yêu cầu Maven kiểm thử lại sau khi xóa output cũ:

```bash
./mvnw clean test
```

Để giới hạn vào một test class với Maven Surefire Plugin được cấu hình phù hợp:

```bash
./mvnw -Dtest=OrderServiceTest test
```

Việc gọi phase `test` cho phép các goal ràng buộc được gọi theo lifecycle, nhưng **plugin riêng** vẫn có thể bỏ qua công việc hoặc dùng cơ chế tối ưu. `clean test` là lựa chọn mạnh hơn khi nghi ngờ class/output cũ, nhưng cũng khiến việc biên dịch và tạo resources phải làm lại. Tránh gọi trực tiếp một goal test riêng lẻ rồi mặc định cho rằng source mới đã được compile: gọi phase `test` thường an toàn hơn vì chạy các phase trước đó.

**Lưu ý:** `-DskipTests` là cách yêu cầu Maven bỏ qua thực thi test trong nhiều cấu hình phổ biến, không phải “ép test chạy lại”. Khi kiểm tra lỗi test cũ, kiểm tra các thuộc tính skip trước khi kết luận test đã thực thi.

## 6. Bảng lệnh nhanh cho Maven và Gradle

| Nhu cầu | Maven Wrapper | Gradle Wrapper |
|---|---|---|
| Xóa đầu ra | `./mvnw clean` | `./gradlew clean` |
| Biên dịch/đóng gói, tận dụng trạng thái sẵn có | `./mvnw package` | `./gradlew build` hoặc `./gradlew bootJar` |
| Build từ thư mục output sạch | `./mvnw clean package` | `./gradlew clean build` |
| Chạy giai đoạn test | `./mvnw test` | `./gradlew test` |
| Chạy test sau khi xóa output | `./mvnw clean test` | `./gradlew clean test` |
| Yêu cầu Gradle thực thi lại test và phụ thuộc | Không có cờ tương đương trực tiếp | `./gradlew test --rerun-tasks` |
| Xem chi tiết vì sao task chạy/skip | Log plugin, `./mvnw -X package` khi cần debug | `./gradlew test --info` hoặc `--debug`, dùng khi cần chẩn đoán |
| Đóng gói Spring Boot executable JAR | `./mvnw package` khi plugin Boot phù hợp được cấu hình | `./gradlew bootJar` khi plugin Boot phù hợp được áp dụng |

**Không nên máy móc thay `mvn package` bằng `gradle build`** trong mọi project. Trên Maven, `package` là phase đóng gói; trên Gradle, `build` còn phụ thuộc vào nhóm task kiểm tra và cấu trúc đồ thị do plugin quyết định. Hãy chọn lệnh dựa trên mục tiêu (test, JAR, kiểm tra toàn bộ) và cấu hình project.

## 7. Thí nghiệm tự quan sát trên một dự án Spring Boot

Bạn có thể dùng project từ Spring Initializr với Java 17+ (hoặc JDK phù hợp với phiên bản Spring Boot đã chọn). Đảm bảo có wrapper, project build hợp lệ và test có thể chạy. Bài tập không yêu cầu sửa cấu hình plugin.

### Thí nghiệm A — Không thay đổi mã nguồn

**Với Gradle:**

```bash
./gradlew clean test --console=plain
./gradlew test --console=plain
```

Quan sát lần thứ hai: các task có input/output ổn định có thể thành `UP-TO-DATE`. Task không có source có thể là `NO-SOURCE`, và task không theo dõi output có thể vẫn chạy. Không khẳng định một số lượng task cụ thể vì phụ thuộc vào project, phiên bản Gradle và plugin.

**Với Maven:**

```bash
./mvnw clean test
./mvnw test
```

Quan sát log compiler/test plugin. Có thể gặp thông báo compiler không cần biên dịch lại, nhưng không kỳ vọng Maven in nhãn `UP-TO-DATE` giống Gradle.

### Thí nghiệm B — Chỉnh một file Java

Sửa một chuỗi, logic hoặc method trong `src/main/java` rồi chạy lại `./gradlew test` hoặc `./mvnw test`. Gradle sẽ xem xét lại các task có input bị ảnh hưởng. Maven kích hoạt các phase/goal tương ứng; plugin sẽ quyết định phần cần biên dịch lại. Một thay đổi ở API hoặc dependency có thể gây biên dịch rộng hơn thay đổi trong phần thân method.

Nếu chỉ sửa test source ở `src/test/java`, các bước liên quan đến biên dịch và thực thi test có khả năng cần chạy lại; mức độ ảnh hưởng phụ thuộc task và plugin. Nếu sửa một file không thuộc input của task (ví dụ README), đa số tác vụ biên dịch sẽ không cần chạy lại, trừ khi build đã khai báo file ấy làm input.

### Thí nghiệm C — Ép chạy lại mà không clean

**Với Gradle:**

```bash
./gradlew test --rerun-tasks --console=plain
```

So sánh trạng thái với lần thứ hai của thí nghiệm A. Theo dõi task nào được thực thi; `build/` không bị xóa trước theo ý nghĩa của cờ rerun. Nếu không có nguồn test hoặc task bị skip theo cấu hình, có thể không thấy test chạy thực tế.

**Với Maven:**

```bash
./mvnw clean test
```

Đây là thí nghiệm **xóa output rồi chạy các phase đến test**, không phải bản sao hoàn toàn của `--rerun-tasks`. Sự khác biệt này chính là điểm cần ghi nhớ khi chuyển đổi giữa hai build tool.

### Thí nghiệm D — Kiểm tra output và build cache

Với Gradle, khi bật build cache và task cacheable, sau khi clean có thể gặp `FROM-CACHE`:

```bash
./gradlew clean build --build-cache --console=plain
```

Không đảm bảo tất cả task cacheable, có cache hit hay output giống nhau giữa mọi máy: điều kiện cache key, trạng thái cache và cấu hình build quyết định kết quả. Nếu muốn quan sát nguyên nhân tối ưu, dùng `--info`; không nên kết luận rằng `FROM-CACHE` là lỗi vì task không chạy action.

## 8. Chọn thao tác nào trong tình huống thực tế?

| Tình huống | Nên thử trước | Vì sao |
|---|---|---|
| Sửa Java hoặc unit test trong lúc phát triển | Build/test bình thường, không clean | Giữ lại output để tối ưu theo thay đổi |
| Chỉ muốn chạy test vừa bị sửa | `test` hoặc lọc test theo plugin | Giảm phạm vi công việc |
| Gradle báo `UP-TO-DATE` nhưng cần kiểm tra lại hành vi test | `test --rerun-tasks` | Buộc các task trong đồ thị liên quan được thực thi |
| Output cục bộ nghi hỏng, file cũ sót lại hoặc kết quả khó giải thích | `clean test` hoặc `clean build/package` | Xóa đầu ra cũ để tái tạo |
| Sau đổi nhánh hoặc đổi cấu hình build quan trọng | Build bình thường, clean nếu dấu hiệu lỗi còn tồn tại | Để tool xác định input nào thay đổi trước |
| CI cần kiểm chứng từ output sạch | Kết hợp clean với các phase/task kiểm tra theo chính sách CI | Hạn chế phụ thuộc vào output tồn tại từ lần chạy trước |
| Cần kiểm tra liệu cache có gây ra khác biệt | Phân biệt clean, rerun và build cache; xem log trạng thái | Clean có thể vẫn khôi phục cache; rerun không xóa output |
| Lỗi thiếu/tải sai dependency | Kiểm tra repository, resolution và cache dependency riêng | Clean output hoặc rerun task không đồng nghĩa làm mới dependency |

Trong CI, dù dùng `clean` có thể là chủ trương tốt của nhóm, vẫn cần quản lý toolchain, dependency locking, plugin versions, secret và artifact provenance nếu muốn có bản build tái lập. `clean` **không tự bảo đảm reproducible build**.

## 9. Các ngộ nhận và lỗi phổ biến

**“Cứ build là phải clean.”** Thực tế, gọi clean mỗi lần sẽ loại bỏ kết quả đang hợp lệ, làm tăng thời gian biên dịch/test. Ưu tiên chạy lệnh thường trước; clean khi nghi ngờ trạng thái output hoặc cần kiểm chứng có chủ đích.

**“Clean luôn làm mọi thứ chạy lại từ đầu.”** Nó xóa đầu ra đã cấu hình, nhưng không nhất thiết xóa cache dependency hoặc build cache; Gradle có thể lấy kết quả từ cache sau clean.

**“Không sửa source thì task chắc chắn UP-TO-DATE.”** Input của task có thể gồm dependency, toolchain, cấu hình plugin, resource, environment hoặc giá trị property. Output bị xóa/sửa hoặc task không khai báo input/output chuẩn cũng ảnh hưởng quyết định chạy.

**“UP-TO-DATE, FROM-CACHE và SKIPPED đều giống nhau.”** Chúng biểu thị các lý do bỏ qua khác nhau. `UP-TO-DATE` tái dùng output đang có, `FROM-CACHE` phục hồi output được cache, còn `SKIPPED` thường do điều kiện thực thi.

**“Rerun task nghĩa là xóa build directory.”** `--rerun-tasks` không cần xóa `build/`; nó hướng vào quyết định thực thi trong task graph. Ngược lại `clean` chỉ xóa output và không chạy lại các task khác nếu không yêu cầu.

**“Gradle --rerun-tasks chỉ chạy task tên ở cuối lệnh.”** Nó áp dụng cho các task thuộc đồ thị cần thiết, kể cả dependency của task yêu cầu. Việc này có thể tốn nhiều thời gian hơn mong đợi.

**“Maven chạy lại phase test là giống hoàn toàn Gradle --rerun-tasks.”** Maven goal/plugin và Gradle task có cơ chế tối ưu khác nhau. Khi cần output sạch trong Maven, chọn `clean test`; khi chỉ cần gọi lại test trong vòng đời, chọn `test`, rồi xem plugin log.

**“Lúc test không chạy nghĩa là build hỏng.”** Có thể project chưa có test source, test task bị disable, test bị skip hoặc test result được tái sử dụng. Hãy kiểm tra log, cấu hình test và report trước khi kết luận.

**“Đã chạy clean là dependency mới được tải lại.”** Không đúng. Maven/Gradle quản lý dependency repository/cache riêng. Nếu vấn đề nằm ở dependency resolution, phải chẩn đoán chúng trực tiếp thay vì chỉ xóa `target/` hay `build/`.

## 10. Checklist để chẩn đoán một lần build

1. **Bạn muốn gì?** Xóa output, rút ngắn thời gian build hay kiểm chứng một task đã chạy lại?
2. **Dùng công cụ nào?** `mvnw`/`pom.xml` là Maven; `gradlew`/`build.gradle[.kts]` là Gradle.
3. **Task/phase nào đã được yêu cầu?** `package`, `test`, `build`, `bootJar` không có phạm vi giống hệt nhau.
4. **Input/output nào thay đổi?** Source, test, resources, dependency, plugin, Java toolchain hoặc output bị xóa.
5. **Log giải thích gì?** Gradle `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED`; Maven thông báo của compiler/test/packaging plugin.
6. **Có cần clean không?** Chỉ khi mục tiêu thật sự cần đầu ra sạch hoặc xử lý trạng thái nghi ngờ.
7. **Có cần ép thực thi không?** Trong Gradle, cân nhắc `--rerun-tasks` cho task graph đã chọn; trong Maven, chọn phase và cơ chế plugin phù hợp.
8. **Kết quả đã được kiểm chứng chưa?** Xem test report, file JAR/WAR và exit code của lệnh; không kết luận chỉ từ thời gian chạy.

### Tài liệu tham khảo chính thức

- [Gradle — Incremental build](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle — Incremental builds and build caching](https://docs.gradle.org/current/userguide/gradle_optimizations.html)
- [Gradle — Command-line interface, forcing tasks to execute](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Maven — Introduction to the build lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)

**Ghi nhớ:** `clean` dọn đầu ra; **build tăng dần** tránh tính lại công việc không cần; **rerun** buộc thực thi lại một phạm vi công việc có chủ đích. Trong Spring Boot, chọn phase/task theo mục tiêu, đọc trạng thái build tool rồi mới quyết định có clean hay ép chạy lại.
