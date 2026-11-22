# Tác vụ tổng hợp và các tác vụ thực sự tạo đầu ra

Khi chạy một lệnh build, bạn thường chỉ gõ một tên tác vụ như `build`, `check`, `assemble` hoặc một giai đoạn như `package`. Tuy nhiên, kết quả cuối cùng thường được tạo bởi nhiều bước nhỏ hơn: biên dịch mã nguồn, xử lý tài nguyên, chạy kiểm thử, tạo báo cáo và đóng gói JAR. Để hiểu một lệnh build thực sự làm gì, cần phân biệt **tác vụ tổng hợp** với **tác vụ thực hiện công việc và tạo đầu ra**.

Tác vụ tổng hợp là điểm vào thuận tiện để yêu cầu một nhóm công việc liên quan. Nó thường khai báo quan hệ phụ thuộc đến các tác vụ khác và không tự tạo một sản phẩm riêng. Các tác vụ ở phía dưới thực hiện công việc cụ thể, chẳng hạn biên dịch `.java` thành `.class`, sao chép tài nguyên, tạo báo cáo kiểm thử hoặc đóng gói JAR.

```text
Người dùng yêu cầu: build
          |
          v
    Tác vụ build
    (tổng hợp)
          |
          +-------------------+
          |                   |
          v                   v
      check               assemble
    (tổng hợp)            (tổng hợp)
          |                   |
          v                   v
        test                 jar
     (kiểm thử)          (đóng gói)
          |                   |
          v                   v
   Báo cáo kết quả       Tệp JAR
   kiểm thử              ứng dụng/thư viện
```

Sơ đồ là mô hình khái quát của Gradle Java plugin. Cây tác vụ thực tế có thể có thêm bước biên dịch, xử lý tài nguyên, plugin và phụ thuộc do dự án khai báo.

## 1. Tác vụ trong build tool là gì?

Trong Gradle, một task là một đơn vị công việc có tên. Task có thể đọc đầu vào, thực hiện một hoặc nhiều hành động, rồi tạo đầu ra. Ví dụ:

- `compileJava` biên dịch mã nguồn Java thành bytecode.
- `processResources` xử lý và sao chép tài nguyên vào thư mục đầu ra.
- `test` chạy kiểm thử tự động và ghi nhận kết quả.
- `jar` đóng gói các lớp và tài nguyên thành một tệp JAR.
- `clean` xóa thư mục đầu ra của project theo cấu hình.

Một task không nhất thiết phải có hành động riêng. Có những task được tạo ra chủ yếu để gom các task khác thành một nhóm có ý nghĩa. Chúng thường được gọi là *lifecycle task* hoặc *aggregate task* (tác vụ vòng đời hoặc tác vụ tổng hợp).

Ví dụ, khi dùng Gradle Java plugin, bạn có thể gọi:

```shell
./gradlew build
```

Trên Windows:

```powershell
.\gradlew.bat build
```

Lệnh này yêu cầu Gradle thực hiện tác vụ `build`. Tác vụ `build` tiêu chuẩn đóng vai trò tổng hợp: nó phụ thuộc vào các nhóm kiểm tra và đóng gói. Việc tạo lớp, chạy test và tạo JAR do các task tương ứng đảm nhiệm.

Không nên hiểu rằng mỗi tên task được gõ ở Terminal đều tương ứng với một tệp đầu ra cùng tên. Tên task là tên một đơn vị công việc trong build graph; tệp được tạo ra phụ thuộc vào hành động và cấu hình của task đó.

## 2. Tác vụ tổng hợp và tác vụ tạo đầu ra khác nhau thế nào?

### Tác vụ tổng hợp

Tác vụ tổng hợp thường có các đặc điểm:

- Đại diện cho một mục tiêu lớn hoặc một giai đoạn của quy trình build.
- Khai báo `dependsOn` đến những task cần thiết.
- Thường không có hành động xử lý riêng và không khai báo artifact đầu ra của chính nó.
- Giúp người dùng gọi một lệnh ngắn thay vì liệt kê nhiều task con.

Trong Gradle Java plugin, các ví dụ quen thuộc là:

| Task | Vai trò tổng hợp |
|---|---|
| `build` | Gom các công việc kiểm tra và đóng gói ứng dụng. |
| `assemble` | Gom các công việc tạo archive/artifact. |
| `check` | Gom các công việc xác minh như kiểm thử. |

`build`, `assemble` và `check` là các điểm vào theo quy ước của plugin. Plugin khác có thể bổ sung task phụ thuộc hoặc tạo thêm lifecycle task.

### Tác vụ thực hiện công việc và tạo đầu ra

Các task thực hiện công việc cụ thể thường có hành động và tạo ra kết quả có thể xác định:

| Task ví dụ | Công việc | Đầu ra thường gặp |
|---|---|---|
| `compileJava` | Biên dịch mã nguồn ứng dụng | `.class` trong `build/classes/java/main/` |
| `processResources` | Sao chép/xử lý tài nguyên ứng dụng | Tệp trong `build/resources/main/` |
| `compileTestJava` | Biên dịch mã nguồn kiểm thử | `.class` trong `build/classes/java/test/` |
| `test` | Chạy kiểm thử | Kết quả test và báo cáo trong `build/test-results/`, `build/reports/` |
| `jar` | Đóng gói lớp và tài nguyên | JAR trong `build/libs/` |
| `bootJar` | Đóng gói ứng dụng Spring Boot có thể chạy | Executable JAR trong `build/libs/` khi plugin Spring Boot được áp dụng |

Đường dẫn trên là vị trí mặc định thường gặp. Dự án có thể cấu hình lại thư mục build, source set hoặc đầu ra của plugin. `bootJar` cũng không phải task có sẵn trong mọi dự án Gradle; nó được cung cấp bởi plugin Spring Boot phù hợp.

### Phân biệt qua câu hỏi đơn giản

Khi gặp một task chưa biết, hãy hỏi:

1. Task này đại diện cho một mục tiêu lớn và phụ thuộc vào các task khác hay trực tiếp thực hiện một công việc?
2. Nó có khai báo đầu vào, đầu ra hoặc hành động cụ thể không?
3. Sau khi chạy, cần tìm kết quả ở đâu?

Một task có tên như `prepareRelease` có thể là task tổng hợp do dự án tự tạo. Một task tên `generateVersionFile` có thể là task tạo tệp. Tên gọi chỉ gợi ý ý định; cần đọc cấu hình task để xác định hành vi thực tế.

## 3. Đồ thị tác vụ (task graph)

Build tool không chỉ chạy một danh sách lệnh theo thứ tự bạn nhìn thấy. Gradle xây dựng một đồ thị tác vụ dựa trên task được yêu cầu và các quan hệ phụ thuộc của nó. Đồ thị này thường được gọi là *task graph*.

Một đồ thị có:

- **Node (nút):** một task cụ thể, chẳng hạn `build`, `compileJava` hoặc `jar`.
- **Dependency edge (cạnh phụ thuộc):** quan hệ cho biết một task cần task khác hoàn tất trước khi thực hiện.
- **Task được yêu cầu:** task mà người dùng gọi trực tiếp từ Terminal hoặc một task khác yêu cầu.

Khi bạn chạy `build`, Gradle bắt đầu từ task đó, lần theo các quan hệ phụ thuộc và đưa những task cần thiết vào đồ thị. Các dependency gián tiếp cũng được đưa vào. Vì vậy, một task có thể chạy dù bạn không gõ tên nó trong lệnh Terminal.

Ví dụ giản lược:

```text
                         build
                        /     \
                       v       v
                    check   assemble
                      |        |
                      v        v
                     test     jar
                      |        |
                      v        v
                 testClasses  classes
                    /   \      /   \
                   v     v    v     v
            compileTest  process  compileJava process
                Java    TestRes              Resources
```

Sơ đồ chỉ minh họa quan hệ phụ thuộc chính theo hướng dễ đọc; đồ thị chi tiết do Gradle tạo ra còn phụ thuộc cấu hình source set, classpath, plugin và các task tùy chỉnh.

Mã kiểm thử thường sử dụng các lớp của ứng dụng trên compile classpath. Gradle theo dõi quan hệ tạo ra những lớp này để đưa các task cần thiết vào đồ thị, vì vậy nhánh kiểm thử có thể kéo theo output `main` dù sơ đồ rút gọn không vẽ mọi cạnh.

### Gradle quyết định task nào cần được đưa vào đồ thị

Giả sử bạn yêu cầu:

```shell
./gradlew jar
```

Gradle không chỉ chạy một thao tác tạo ZIP/JAR ngay lập tức. Task `jar` cần lớp và tài nguyên đã được xử lý, nên các task phụ thuộc tương ứng cũng được đưa vào đồ thị. Nếu đầu ra biên dịch chưa tồn tại hoặc đã cũ, task biên dịch có thể phải thực hiện. Nếu đầu ra vẫn hợp lệ, Gradle có thể bỏ qua hành động của task đó.

Nếu yêu cầu:

```shell
./gradlew build
```

đồ thị rộng hơn vì `build` yêu cầu cả các nhánh kiểm tra và đóng gói. Do đó, `build` có thể chạy test và tạo JAR dù bạn không gọi trực tiếp `test` hay `jar`.

### Thứ tự và khả năng chạy song song

Quan hệ phụ thuộc bảo đảm task phụ thuộc chỉ được thực hiện sau khi các dependency cần thiết hoàn tất. Tuy nhiên, những dependency độc lập có thể được Gradle chạy song song nếu cấu hình và tài nguyên cho phép.

Ví dụ, hai task không phụ thuộc lẫn nhau có thể được chạy đồng thời. Không nên dựa vào thứ tự tình cờ trong log nếu build script chưa khai báo quan hệ cần thiết. Nếu task B thật sự cần đầu ra của task A, hãy khai báo phụ thuộc dữ liệu hoặc `dependsOn` phù hợp.

## 4. `dependsOn`: khai báo phụ thuộc thực sự

`dependsOn` là cách phổ biến để nói rằng một task cần các task khác hoàn tất trước khi chính nó được thực hiện.

Với Gradle Java plugin, task `build` tiêu chuẩn đã được cấu hình sẵn để phụ thuộc vào `check` và `assemble`. Vì vậy, khi chạy `build`, bạn không cần tự thêm các dependency đó một lần nữa.

Bạn có thể tạo một task tổng hợp riêng cho quy trình phát hành:

```groovy
plugins {
    id 'java'
}

tasks.register('prepareRelease') {
    group = 'build'
    description = 'Chuẩn bị các đầu ra cần thiết cho một bản phát hành.'

    dependsOn tasks.named('jar')
    dependsOn tasks.named('test')
}
```

Trong ví dụ, `prepareRelease` không tự biên dịch mã nguồn, không chạy test và không tạo JAR. Nó yêu cầu Gradle thực hiện `jar` và `test`. Các task này tiếp tục kéo theo những dependency cần thiết của chúng.

Bạn cũng có thể khai báo nhiều dependency trong một lần:

```groovy
tasks.register('prepareRelease') {
    dependsOn tasks.named('jar'), tasks.named('test')
}
```

`tasks.named(...)` lấy tham chiếu đến task theo cách hỗ trợ cấu hình trì hoãn (lazy configuration). Cách này phù hợp với mô hình task configuration avoidance của Gradle và tránh buộc phải tạo/cấu hình task sớm hơn cần thiết.

### Dependency gián tiếp

Nếu `prepareRelease` phụ thuộc `jar`, và `jar` phụ thuộc `classes`, thì `classes` là dependency gián tiếp của `prepareRelease`. Bạn không cần khai báo lại toàn bộ cây dependency bằng tay.

```text
prepareRelease
      |
      v
     jar
      |
      v
   classes
      |
      +------> compileJava
      |
      +------> processResources
```

Đồ thị phụ thuộc là cơ chế giúp build tool biết các bước cần thiết để tạo kết quả. Khi một task cần tệp do task khác tạo ra, hãy khai báo mối quan hệ đó thay vì giả định task kia đã chạy trước.

## 5. Phân biệt `dependsOn`, `mustRunAfter` và `shouldRunAfter`

Ba cơ chế này thường bị nhầm lẫn vì đều liên quan đến thứ tự task, nhưng ý nghĩa khác nhau.

| Cơ chế | Ý nghĩa | Tự đưa task kia vào đồ thị? |
|---|---|---|
| `dependsOn` | Task hiện tại cần dependency hoàn tất trước. | Có. |
| `mustRunAfter` | Nếu cả hai task đã được chọn, task hiện tại phải chạy sau task kia. | Không. |
| `shouldRunAfter` | Nếu cả hai task đã được chọn, ưu tiên chạy task hiện tại sau task kia khi có thể. | Không. |
| `finalizedBy` | Đăng ký task chạy sau task được finalize, kể cả khi task chính thất bại. | Có, khi task chính được đưa vào đồ thị. |

Ví dụ:

```groovy
tasks.register('publishReport') {
    mustRunAfter tasks.named('test')
}
```

Khai báo này không có nghĩa là chỉ cần chạy `publishReport` thì Gradle tự chạy `test`. Nó chỉ quy định thứ tự khi cả `test` và `publishReport` đã được chọn vào cùng đồ thị.

Nếu muốn `publishReport` luôn yêu cầu kết quả test được tạo trước, hãy dùng dependency:

```groovy
tasks.register('publishReport') {
    dependsOn tasks.named('test')
}
```

Ví dụ về finalizer:

```groovy
tasks.register('stopTestService') {
    doLast {
        println 'Dừng dịch vụ kiểm thử.'
    }
}

tasks.named('test') {
    finalizedBy tasks.named('stopTestService')
}
```

Khi task `test` được chọn, task finalizer cũng được đưa vào đồ thị để chạy sau `test`, kể cả khi `test` kết thúc thất bại. Cơ chế này hữu ích cho công việc dọn dẹp hoặc kết thúc tài nguyên đã được khởi tạo. Cần thiết kế finalizer an toàn vì nó có thể chạy sau một lần test lỗi.

Không dùng `mustRunAfter` thay cho `dependsOn` khi task thực sự cần đầu ra của task khác. Ràng buộc thứ tự không tự bảo đảm đầu ra cần thiết đã được tạo.

## 6. Các task tiêu chuẩn của Gradle Java plugin

Gradle Java plugin cung cấp một tập task theo quy ước. Hiểu vai trò của chúng giúp bạn lần theo đồ thị khi chạy `build`.

### Nhóm biên dịch và xử lý tài nguyên

| Task | Vai trò |
|---|---|
| `compileJava` | Biên dịch mã nguồn Java của source set `main`. |
| `processResources` | Sao chép hoặc xử lý tài nguyên của `main`. |
| `classes` | Task tổng hợp đầu ra chính: phụ thuộc vào biên dịch và xử lý tài nguyên. |
| `compileTestJava` | Biên dịch mã nguồn Java của source set `test`. |
| `processTestResources` | Xử lý tài nguyên kiểm thử. |
| `testClasses` | Gom các đầu ra cần thiết để có lớp kiểm thử. |

`classes` và `testClasses` là các task tổng hợp trong quy trình biên dịch. Chúng giúp các task phía sau yêu cầu một nhóm đầu ra bằng một tên thống nhất.

### Nhóm kiểm thử

`test` chạy các kiểm thử của source set `test`. Nó cần các lớp kiểm thử và lớp ứng dụng tương ứng. Trong cấu hình tiêu chuẩn, task này tạo dữ liệu kết quả và báo cáo kiểm thử, thường dưới `build/test-results/test/` và `build/reports/tests/test/`.

`check` là task tổng hợp cho các bước xác minh. Nó phụ thuộc vào `test` và có thể nhận thêm dependency từ plugin kiểm tra chất lượng hoặc task kiểm tra do dự án khai báo.

### Nhóm đóng gói

`jar` đóng gói lớp và tài nguyên của source set `main` thành JAR. Nó cần đầu ra `classes`, vì vậy các bước biên dịch và xử lý tài nguyên được thực hiện trước nếu cần.

`assemble` là task tổng hợp cho các đầu ra có thể lắp ráp/phân phối. Với Java plugin, nó phụ thuộc vào task archive như `jar`. Plugin khác có thể thêm các archive task khác vào `assemble`.

### Task `build`

`build` là điểm vào tổng hợp cấp cao của Java plugin. Nó kết hợp hai nhóm lớn:

- `check`: xác minh chất lượng và chạy kiểm thử.
- `assemble`: tạo các archive/artifact.

Vì vậy, một lần chạy `build` thành công cho biết toàn bộ task cần thiết trong đồ thị đã hoàn tất theo trạng thái thành công, bỏ qua hợp lệ hoặc dùng lại kết quả phù hợp. Nó không có nghĩa tồn tại một tệp tên `build` hay chính task `build` đã tự tạo JAR.

## 7. Ví dụ task tổng hợp và task tạo tệp do dự án tự viết

Để thấy rõ sự khác biệt, hãy tạo một task ghi phiên bản phát hành ra tệp và một task tổng hợp yêu cầu cả JAR lẫn tệp phiên bản.

Ví dụ dưới đây dùng Groovy DSL trong `build.gradle` và giả định dự án đã áp dụng Java plugin:

```groovy
plugins {
    id 'java'
}

def releaseVersion = providers.gradleProperty('releaseVersion').orElse('1.0.0')
def versionFile = layout.buildDirectory.file('generated/version/version.txt')

tasks.register('generateVersionFile') {
    group = 'build'
    description = 'Ghi phiên bản phát hành vào tệp.'

    inputs.property('releaseVersion', releaseVersion)
    outputs.file(versionFile)

    doLast {
        def output = versionFile.get().asFile
        output.parentFile.mkdirs()
        output.text = releaseVersion.get() + '\n'
    }
}

tasks.register('prepareRelease') {
    group = 'build'
    description = 'Chuẩn bị JAR và tệp phiên bản.'

    dependsOn tasks.named('jar')
    dependsOn tasks.named('generateVersionFile')
}
```

Trong ví dụ:

- `generateVersionFile` có hành động `doLast`, ghi nội dung vào một tệp cụ thể.
- `inputs.property(...)` khai báo giá trị phiên bản là đầu vào của task.
- `outputs.file(...)` khai báo tệp được tạo là đầu ra của task.
- `prepareRelease` chỉ gom `jar` và `generateVersionFile` bằng `dependsOn`; bản thân nó không tạo tệp.

Chạy task tổng hợp:

```shell
./gradlew prepareRelease
```

Trên Windows:

```powershell
.\gradlew.bat prepareRelease
```

Sau khi chạy, các kết quả chính có thể gồm:

```text
build/
├── generated/
│   └── version/
│       └── version.txt
├── classes/
│   └── java/
│       └── main/
└── libs/
    └── ten-du-an-1.0.0.jar
```

`prepareRelease` là điểm gọi tiện lợi. `generateVersionFile` và `jar` mới là các task trực tiếp tạo ra hai đầu ra trong ví dụ.

Nếu muốn đổi phiên bản khi chạy:

```shell
./gradlew prepareRelease -PreleaseVersion=2.1.0
```

Giá trị đầu vào thay đổi nên Gradle cần thực hiện lại task tạo tệp phiên bản. Task `jar` chỉ chạy lại nếu đầu vào hoặc đầu ra của nó cần được cập nhật theo quy tắc của task đó.

## 8. Đầu vào, đầu ra và trạng thái thực thi của task

Gradle cần biết task phụ thuộc vào dữ liệu nào và tạo ra dữ liệu nào để đánh giá có cần chạy lại hay không. Đây là nền tảng của incremental build và build cache.

### Khai báo đầu vào và đầu ra

Với task tùy chỉnh, hãy khai báo rõ:

- **Inputs:** tệp, thư mục, giá trị cấu hình hoặc dữ liệu mà hành động đọc.
- **Outputs:** tệp hoặc thư mục mà hành động tạo/cập nhật.

Ví dụ task ở phần trước khai báo phiên bản là input và `version.txt` là output. Nếu giá trị phiên bản không đổi và tệp đầu ra vẫn hợp lệ, Gradle có thể đánh dấu task `UP-TO-DATE` thay vì chạy lại hành động.

Nếu task tạo tệp nhưng không khai báo output, Gradle không có đủ thông tin để so sánh đầu ra theo cách mong muốn. Task có thể phải chạy lại ở những lần build tiếp theo và không tận dụng đầy đủ cơ chế kiểm tra trạng thái hoặc cache.

### Các trạng thái thường thấy trong log

| Trạng thái | Ý nghĩa khái quát |
|---|---|
| Không có hậu tố đặc biệt / task thực thi | Gradle đã chạy hành động của task. |
| `UP-TO-DATE` | Đầu vào và đầu ra được xem là không thay đổi; không cần chạy lại hành động. |
| `FROM-CACHE` | Gradle khôi phục đầu ra từ build cache phù hợp. |
| `NO-SOURCE` | Không có tệp nguồn phù hợp để task xử lý. |
| `SKIPPED` | Task được bỏ qua theo điều kiện hoặc cơ chế thực thi; xem lý do trong log. |
| `FAILED` | Task thất bại khi thực hiện. |

Một task có trong đồ thị không đồng nghĩa hành động của nó luôn chạy. Task có thể được đưa vào đồ thị nhưng được đánh dấu `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` hoặc `SKIPPED` tùy trạng thái.

Đặc biệt, tác vụ tổng hợp thường không có hành động và không tạo output riêng. Vai trò của nó là đảm bảo các task phụ thuộc được yêu cầu. Vì vậy, hãy quan sát task con và đầu ra của chúng để hiểu build đã tạo gì.

### Build cache không phải artifact phát hành

Build cache lưu kết quả của các task đủ điều kiện để có thể dùng lại khi đầu vào tương ứng giống nhau. Nó là cơ chế tăng tốc build. JAR trong `build/libs/` hoặc báo cáo kiểm thử là output của task; cache là nơi Gradle có thể lưu và khôi phục một số output đó. Không nên nhầm thư mục cache với thư mục artifact mà nhóm phát triển cần phân phối.

## 9. Quan sát task graph trước khi thực thi

Khi chưa rõ một lệnh sẽ gọi những task nào, bạn có thể yêu cầu Gradle hiển thị đồ thị dự kiến.

### Liệt kê task có sẵn

```shell
./gradlew tasks
```

Để xem cả task nâng cao hoặc task không được liệt kê trong nhóm mặc định:

```shell
./gradlew tasks --all
```

Trên Windows:

```powershell
.\gradlew.bat tasks --all
```

### Xem thông tin của một task

```shell
./gradlew help --task build
./gradlew help --task jar
```

Thông tin này giúp xác định task có sẵn trong project, nhóm và mô tả của nó. Nó không thay thế việc đọc build script khi cần hiểu dependency hoặc hành động cụ thể.

### Chạy thử đồ thị bằng `--dry-run`

```shell
./gradlew build --dry-run
```

`--dry-run` yêu cầu Gradle xây dựng và hiển thị các task trong đồ thị mà không thực hiện hành động của chúng. Các task thường được hiển thị với trạng thái `SKIPPED` do chế độ dry run. Đây là cách hữu ích để xem một task tổng hợp kéo theo những task nào trước khi chạy build thật.

Với dự án nhiều module:

```shell
./gradlew :app:build --dry-run
```

Tên `:app:build` chỉ rõ task `build` trong project con `app`. Cú pháp đường dẫn task giúp phân biệt task cùng tên ở nhiều module.

### Xem log chi tiết

```shell
./gradlew build --info
```

`--info` cung cấp thêm thông tin về quá trình thực thi, trạng thái task và một số quyết định của Gradle. Khi cần tìm nguyên nhân lỗi sâu hơn, có thể dùng `--stacktrace`; chỉ bật log chi tiết hơn khi cần vì đầu ra có thể dài.

## 10. Tác vụ tổng hợp trong dự án nhiều module

Trong dự án nhiều module, mỗi subproject có thể khai báo task riêng và có thư mục đầu ra riêng. Task tổng hợp ở root project có thể gom công việc từ nhiều module.

Ví dụ cấu trúc:

```text
workspace/
├── settings.gradle
├── build.gradle
├── app/
│   └── build.gradle
├── domain/
│   └── build.gradle
└── infrastructure/
    └── build.gradle
```

Nếu chạy:

```shell
./gradlew build
```

Gradle có thể chạy task `build` của root project và các subproject theo cấu hình của build. Các task trong `app`, `domain` và `infrastructure` có thể phụ thuộc lẫn nhau qua project dependency. Gradle xác định các dependency cần thiết để biên dịch và đóng gói theo đồ thị.

Bạn cũng có thể chỉ định một module:

```shell
./gradlew :domain:build
```

Lệnh này yêu cầu build cho module `domain`. Nếu module có dependency đến project khác, các task cần thiết của dependency có thể được đưa vào đồ thị. Việc chỉ định một project không có nghĩa Gradle bỏ qua mọi dependency mà project đó cần.

Với module, cần phân biệt:

- Task tổng hợp ở root: điều phối một mục tiêu trên nhiều project.
- Task tổng hợp trong module: gom các công việc của module đó.
- Task tạo đầu ra trong module: tạo `.class`, resource, báo cáo hoặc artifact ở thư mục build của module.

Khi tìm JAR, hãy xem đúng thư mục `build/libs/` của project tạo ra nó, không mặc định mọi artifact đều nằm ở root.

## 11. Maven: phase tổng hợp và plugin goal thực hiện công việc

Gradle mô hình hóa quy trình qua task graph. Maven dùng khái niệm lifecycle, phase và plugin goal. Hai công cụ có cách tổ chức khác nhau, nhưng vẫn có thể phân biệt điểm gọi cấp cao với thao tác thực sự tạo đầu ra.

Trong Maven, `package` là một **lifecycle phase**. Khi chạy:

```shell
mvn package
```

Maven thực hiện các phase trước đó trong lifecycle mặc định rồi đến `package`. Các plugin goal được gắn với những phase tương ứng mới thực hiện công việc cụ thể. Với một dự án Java đóng gói JAR, ví dụ thường gặp:

| Phase | Plugin goal thường thực hiện |
|---|---|
| `compile` | Compiler plugin biên dịch mã nguồn chính thành `target/classes/`. |
| `test-compile` | Compiler plugin biên dịch mã nguồn test thành `target/test-classes/`. |
| `test` | Surefire plugin chạy unit test và tạo báo cáo. |
| `package` | JAR plugin đóng gói thành tệp `.jar` trong `target/`. |

Các goal cụ thể phụ thuộc `pom.xml`, packaging, phiên bản plugin và cấu hình. Phase là điểm mốc trong lifecycle; plugin goal gắn với phase mới là đơn vị thực hiện công việc cụ thể.

Bạn có thể gọi trực tiếp một plugin goal, ví dụ:

```shell
mvn jar:jar
```

Lệnh trực tiếp này gọi goal `jar` của plugin JAR. Khi dùng `mvn package`, Maven đi qua lifecycle và thực hiện goal được gắn vào phase `package` theo cấu hình dự án.

Gọi trực tiếp một goal không tự động chạy toàn bộ các phase trước đó của lifecycle. Vì vậy, nếu gọi `jar:jar` riêng, hãy bảo đảm các lớp và tài nguyên đầu vào đã được tạo hoặc có sẵn ở đúng vị trí.

Không nên xem Maven phase và Gradle task là hai khái niệm hoàn toàn giống nhau. Tuy nhiên, cách suy nghĩ sau hữu ích cho cả hai: điểm vào cấp cao yêu cầu một quy trình; các goal/task cụ thể đọc đầu vào, thực hiện hành động và tạo đầu ra.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Chạy `build` nghĩa là task `build` tự biên dịch và tạo JAR | `build` là task tổng hợp; các task phụ thuộc như biên dịch và `jar` thực hiện công việc cụ thể. |
| `dependsOn` chỉ sắp xếp thứ tự hai task đã chọn | `dependsOn` còn đưa dependency vào đồ thị nếu nó chưa được chọn. |
| `mustRunAfter` tự chạy task được nhắc đến | Nó chỉ ràng buộc thứ tự khi cả hai task đã có trong đồ thị. |
| Mọi task trong đồ thị đều chạy hành động | Task có thể `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` hoặc bị bỏ qua. |
| `assemble` là tên tệp đầu ra | Đây thường là task tổng hợp các công việc đóng gói; artifact cụ thể được tạo bởi task như `jar`. |
| `check` tự chạy tất cả mọi loại kiểm tra trong mọi dự án | Nó gom các task xác minh đã được plugin hoặc dự án gắn vào. |
| `test` và `build` tạo cùng một loại đầu ra | `test` tạo kết quả/báo cáo kiểm thử; `build` yêu cầu các nhóm kiểm tra và đóng gói. |
| Thứ tự log luôn là thứ tự cần dựa vào trong build script | Hãy khai báo dependency hoặc ordering rule phù hợp; các task độc lập có thể chạy song song. |
| Maven `package` là một plugin goal | `package` là lifecycle phase; các plugin goal được gắn vào phase thực hiện công việc. |

## 13. Cách lần theo một lệnh build khi có lỗi

Khi một lệnh tổng hợp thất bại, đừng chỉ nhìn tên task cấp cao. Hãy tìm task cụ thể gây lỗi trong log.

1. Xác định lệnh đã chạy, ví dụ `./gradlew build` hoặc `mvn package`.
2. Với Gradle, dùng `--dry-run` để quan sát các task trong đồ thị nếu chưa rõ dependency.
3. Đọc log để tìm task đầu tiên có trạng thái `FAILED` và thông báo lỗi liên quan.
4. Xác định task đó là task biên dịch, xử lý resource, kiểm thử, đóng gói hay task tùy chỉnh.
5. Kiểm tra input, output, dependency và cấu hình của đúng task.
6. Chạy trực tiếp task gây lỗi hoặc task nhỏ nhất có thể tái hiện lỗi.
7. Sau khi sửa, chạy lại task đó rồi chạy task tổng hợp để xác nhận toàn bộ quy trình.

Ví dụ, nếu `./gradlew build` thất bại tại `:app:compileJava`, vấn đề nằm ở bước biên dịch của module `app`. Chạy lại `build` nhiều lần mà không xử lý lỗi compiler sẽ không làm task tổng hợp tự khắc phục được. Nếu lỗi nằm ở `:app:test`, hãy xem báo cáo test. Nếu lỗi nằm ở `:app:jar`, hãy kiểm tra cấu hình archive và đầu ra mà task đóng gói sử dụng.

Nếu `build` thành công nhưng bạn không tìm thấy JAR, hãy xác nhận đồ thị có chứa task `jar` hoặc task đóng gói tương ứng hay không. Có thể dự án không áp dụng Java plugin, artifact được tạo bởi task khác, task archive đã bị tắt hoặc vị trí đầu ra đã được tùy chỉnh.

## 14. Bài thực hành

Thực hành trên một dự án Gradle sử dụng Java plugin. Nếu đang học Maven, hãy làm phần đối chiếu lifecycle ở cuối bài.

1. Chạy `./gradlew tasks --all` và tìm các task `build`, `assemble`, `check`, `classes`, `test`, `jar`.
2. Chạy `./gradlew build --dry-run`. Ghi lại các task xuất hiện và phân nhóm task tổng hợp với task thực hiện công việc cụ thể.
3. Chạy `./gradlew build` rồi kiểm tra `build/classes/`, `build/resources/`, `build/reports/` và `build/libs/`.
4. Chạy riêng `./gradlew test` và quan sát những task nào được đưa vào đồ thị.
5. Tạo một task `generateVersionFile` có input là phiên bản và output là một tệp trong `build/generated/`.
6. Tạo task tổng hợp `prepareRelease` phụ thuộc `jar` và `generateVersionFile`. Chạy task này và xác định task nào trực tiếp tạo từng đầu ra.
7. Chạy lại `prepareRelease` mà không thay đổi input. Quan sát task nào được đánh dấu `UP-TO-DATE`.
8. Thay giá trị phiên bản, chạy lại và xem task tạo tệp có được thực hiện lại không.
9. Thử dùng `mustRunAfter` trong một ví dụ nhỏ, sau đó chạy riêng từng task để quan sát rằng ràng buộc thứ tự không tự đưa task kia vào đồ thị.
10. Chạy `mvn package` trên một dự án Maven nếu có, rồi xác định phase nào gọi compiler, Surefire và JAR plugin goal.

Sau bài thực hành, bạn cần giải thích được vì sao `build` có thể tạo nhiều kết quả dù bản thân nó không tạo artifact, task graph được hình thành từ đâu, `dependsOn` khác ràng buộc thứ tự như thế nào, và cách tìm task thực sự tạo ra tệp cần dùng. Đây là kỹ năng quan trọng để đọc build script, tối ưu quy trình build và xác định đúng nguyên nhân khi một lệnh tổng hợp thất bại.
