# Theo dấu một lệnh build qua toàn bộ vòng đời Gradle

## 1. Mục tiêu: hiểu Gradle làm gì từ lúc nhận lệnh đến lúc trả kết quả

Khi chạy `./gradlew build`, màn hình thường hiện hàng loạt task như `compileJava`, `test` và `jar`. Nhưng các task đó chỉ là **phần dễ quan sát nhất**. Trước khi thực thi một task, Gradle đã xác định build nào đang được chạy, các project nào tham gia, plugin và cấu hình của chúng, task nào thuộc yêu cầu của người dùng và những quan hệ thứ tự cần tuân theo.

Một cách theo dấu lệnh build có ích là đặt sáu câu hỏi theo thứ tự:

1. **Lệnh nào khởi động Gradle?** Dùng Wrapper hay Gradle được cài trên máy? Yêu cầu task và tham số là gì?
2. **Gradle đang làm việc với build/project nào?** File `settings.gradle` nói gì về tên và thành phần build?
3. **Build được cấu hình thế nào?** File `build.gradle` và plugin tạo/cấu hình những task, dependency và thuộc tính gì?
4. **Task nào được chọn?** Yêu cầu trực tiếp là gì và các task phụ thuộc nào được thêm vào kế hoạch?
5. **Task đã làm gì?** Task action có chạy không, hay Gradle bỏ qua vì không có nguồn/đã cập nhật/khôi phục từ cache?
6. **Kết quả ở đâu và có thành công không?** File đầu ra, báo cáo, exit code và nguyên nhân lỗi nằm ở giai đoạn nào?

Bài học sẽ đi qua đúng luồng này với một ví dụ **có thể chạy**, rồi đối chiếu với `build` của dự án Java thực tế.

## 2. Ba giai đoạn và một bước chuẩn bị trước chúng

Mô hình vòng đời cơ bản của Gradle là:

```text
Người dùng: ./gradlew build
              |
              v
[Chuẩn bị môi trường] Wrapper / Gradle / JVM / tham số
              |
              v
[1. INITIALIZATION] Xác định build, đọc settings, xác định các project
              |
              v
[2. CONFIGURATION] Đánh giá cấu hình cần thiết, áp dụng plugin,
                   đăng ký/cấu hình task và quan hệ
              |
              v
[CHỌN TASK / TASK GRAPH] Xác định tập task cho yêu cầu hiện tại
              |
              v
[3. EXECUTION] Lập lịch và xử lý task theo quan hệ phụ thuộc
              |
              v
[RESULT] BUILD SUCCESSFUL / BUILD FAILED; output, báo cáo
```

**Initialization (khởi tạo):** Gradle xác định build và các project tham gia. File `settings.gradle` (hoặc `settings.gradle.kts`) thường thiết lập `rootProject.name`, `include` các project con, cấu hình quản lý plugin và kho phụ thuộc ở mức settings nếu có.

**Configuration (cấu hình):** Gradle xây dựng mô hình project và task từ build script, plugin và các cấu hình liên quan. Trong `build.gradle`, việc gọi `tasks.register` khai báo task; khối `dependencies` mô tả thư viện; `tasks.named(...)` cấu hình task đã tồn tại. Các hành động trong `doLast`/**`@TaskAction`** chưa phải chạy chỉ vì chúng được định nghĩa.

**Execution (thực thi):** Gradle thực hiện kế hoạch task theo các quan hệ phụ thuộc và thứ tự. Mỗi task có thể thực sự chạy action hoặc được đánh dấu bằng một trạng thái cho thấy action không cần/chưa thể chạy.

**Task graph** không phải một “giai đoạn thứ tư” độc lập trong mô hình ba giai đoạn truyền thống. Nó là kết quả của việc chọn task và xác định quan hệ thực thi trên cơ sở mô hình đã cấu hình. Để học dễ hơn, sơ đồ tách nó thành một chặng quan sát giữa configuration và execution.

Điều cần giữ trong đầu: **đọc build script không đồng nghĩa chạy lần lượt các task đã được viết trong script**.

## 3. Bắt đầu từ lệnh: Wrapper, project hiện tại và tên task

Trong thư mục có file Wrapper của dự án, trên Linux/macOS chạy:

```bash
./gradlew build
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat build
```

`gradlew` và `gradlew.bat` là các script của **Gradle Wrapper**. Chúng dùng cấu hình ở `gradle/wrapper/gradle-wrapper.properties` để xác định bản Gradle dự án yêu cầu; nếu bản đó chưa có, Wrapper có thể tải về. Vì vậy Wrapper giúp các máy trong nhóm nhất quán hơn việc gọi một bản `gradle` cài riêng, nhưng vẫn cần JVM và các điều kiện mạng/phụ thuộc phù hợp.

Trước khi đọc `settings.gradle`, quá trình khởi động còn xác định những tùy chọn dòng lệnh: tên task được yêu cầu, mức log, chế độ offline, cấu hình cache, v.v. **Wrapper không phải một task của Java plugin**; nó là cách khởi động công cụ.

Ba lệnh sau có ý nghĩa khác nhau:

| Lệnh | Yêu cầu |
| --- | --- |
| `./gradlew help` | Chạy task trợ giúp, thường không cần biên dịch mã |
| `./gradlew test` | Chọn task `test` của project phù hợp cùng các task nó phụ thuộc |
| `./gradlew build` | Chọn vòng build do plugin và cấu hình của project định nghĩa |

Trong build nhiều project, `./gradlew :app:build` chỉ rõ task `build` của project `app`. Dấu `:` đầu tiên là đường dẫn từ root project; nó không phải tên thư mục nguồn `src`.

Lưu ý môi trường: Wrapper, Gradle Daemon và việc tải dependency có thể sinh log trước/sau các dấu vết của build script. Vì vậy để theo dấu chính xác, ta sẽ chủ động in **nhãn giai đoạn** từ file cấu hình và **nhãn hành động** từ task.

## 4. Một dự án thực hành tối thiểu với đầu ra có thể dự đoán

Tạo thư mục `lifecycle-trace` và hai file:

```text
lifecycle-trace/
├── settings.gradle
└── build.gradle
```

**File `settings.gradle` (Groovy DSL):**

```groovy
println '[INIT] settings.gradle được đánh giá'
rootProject.name = 'lifecycle-trace'
```

**File `build.gradle`:**

```groovy
plugins {
    id 'base'
}

println '[CONFIG] build.gradle được đánh giá'

tasks.register('prepareData') {
    group = 'learning'
    description = 'Giả lập bước chuẩn bị dữ liệu cho báo cáo'

    doLast {
        println '[EXEC] prepareData'
    }
}

tasks.register('makeReport') {
    group = 'learning'
    description = 'Giả lập bước tạo báo cáo'
    dependsOn(tasks.named('prepareData'))

    doLast {
        println '[EXEC] makeReport'
    }
}
```

Plugin `base` cung cấp các task vòng đời cơ bản; bản thân hai task `prepareData` và `makeReport` do ta tự đăng ký. Chúng không cần mã Java và không dùng thư viện ngoài nên ví dụ tập trung hoàn toàn vào thứ tự xử lý.

Nếu dự án **đã có Wrapper** do công cụ/IDE tạo, dùng Wrapper hiện có. Với một thư mục mới chỉ có hai file trên, cần cài sẵn một bản Gradle tương thích để tạo Wrapper một lần:

```bash
gradle wrapper
```

Lệnh này tạo các file `gradlew`, `gradlew.bat` và `gradle/wrapper/...`. Lệnh tạo Wrapper cũng là một lần chạy Gradle, nên các dòng `[INIT]`/`[CONFIG]` có thể xuất hiện khi thiết lập.

Bây giờ chạy trên Linux/macOS:

```bash
./gradlew --no-configuration-cache --console=plain -q makeReport
```

Hoặc Windows PowerShell:

```powershell
.\gradlew.bat --no-configuration-cache --console=plain -q makeReport
```

Các **dòng do chính ví dụ in ra**, theo thứ tự, là:

```text
[INIT] settings.gradle được đánh giá
[CONFIG] build.gradle được đánh giá
[EXEC] prepareData
[EXEC] makeReport
```

Ở đây `-q` giảm log của Gradle và `--console=plain` giúp log ít phụ thuộc giao diện terminal. `--no-configuration-cache` giúp dễ lặp lại thí nghiệm ngay cả khi cấu hình máy/dự án bật configuration cache. Có thể có thông báo môi trường ngoài bốn dòng được minh họa, nhưng **thứ tự của bốn nhãn trong ví dụ** là cơ sở để kiểm tra tư duy.

Hãy đọc kết quả theo đúng chiều thời gian:

1. `[INIT]` xuất hiện khi Gradle đánh giá settings và xác định root project.
2. `[CONFIG]` xuất hiện trong lúc cấu hình build, chưa thực thi hai hành động `doLast`.
3. `[EXEC] prepareData` xuất hiện trước vì `makeReport` có `dependsOn`.
4. `[EXEC] makeReport` xuất hiện sau khi bước chuẩn bị hoàn tất.

Không có quy tắc “task được viết trước thì chạy trước” trong ví dụ. Thứ tự hành động đến từ **quan hệ phụ thuộc**, không phải vị trí của hai khối `tasks.register` trong file.

## 5. Theo dõi initialization: Gradle quyết định build nào đang chạy

Trong ví dụ, dòng:

```groovy
rootProject.name = 'lifecycle-trace'
```

đặt tên root project. Ở dự án nhiều project, file settings có thể khai báo:

```groovy
rootProject.name = 'shop'
include 'api', 'service'
```

Khi đó Gradle biết có root project `:` và các project con như `:api`, `:service`. Mỗi project có thể áp dụng plugin riêng và có task riêng. Khái niệm **build** (nhóm project do settings điều phối) rộng hơn một **task**, và một project cũng không đồng nghĩa một source set Java.

Dấu hiệu thường gặp của lỗi trong initialization:

- File settings sai cú pháp hoặc cấu hình plugin management không hợp lệ.
- Tên/path project con được khai báo nhưng cấu hình thư mục không phù hợp.
- Không thể khởi tạo môi trường Gradle hoặc giải quyết phần cấu hình ở giai đoạn settings.

Ở giai đoạn này, không thể kết luận lỗi do `compileJava` hay `test` vì chúng chưa thực thi. Đọc **đầu tiên là thông báo Gradle nêu file và dòng lỗi**; nếu đó là `settings.gradle`, điểm bắt đầu điều tra thường nằm ở initialization.

**Không nên đồng nhất** mọi dòng log xuất hiện trước task đầu tiên với initialization: một phần có thể thuộc khởi động Daemon, tải Gradle, kiểm tra JVM hoặc configuration.

## 6. Theo dõi configuration: đăng ký task khác với chạy task

Trong `build.gradle` mẫu, lệnh:

```groovy
tasks.register('prepareData') {
    doLast {
        println '[EXEC] prepareData'
    }
}
```

có hai lớp ý nghĩa:

- `tasks.register('prepareData')` đăng ký một task theo cơ chế cấu hình theo nhu cầu (**configuration avoidance**). Gradle có thể trì hoãn việc hiện thực hóa/cấu hình chi tiết task cho đến khi cần.
- `doLast { ... }` khai báo hành động sẽ được gọi **khi task thực thi**. Nó không chạy trong lúc Gradle đánh giá script ở mức cao nhất.

Ngược lại, dòng:

```groovy
println '[CONFIG] build.gradle được đánh giá'
```

nằm ở cấp cao nhất của script và vì thế được thực hiện khi Gradle đánh giá script trong configuration. Đó là lý do ngay cả lệnh chỉ xem trợ giúp cũng có thể in dấu `[CONFIG]`.

Thử chạy:

```bash
./gradlew --no-configuration-cache --console=plain -q help
```

Thông thường bạn vẫn thấy `[INIT]` và `[CONFIG]` của ví dụ, nhưng không thấy `[EXEC] prepareData` hoặc `[EXEC] makeReport` vì không yêu cầu hai task đó. Gradle vẫn cần mô hình cấu hình phù hợp để chọn/xử lý mục tiêu `help`.

**Bài học thiết kế:** Không đặt thao tác ghi file, gọi dịch vụ, chạy lệnh hệ thống hoặc thay đổi dữ liệu thật ở cấp cao nhất của `build.gradle` chỉ để “làm cho build hoạt động”. Các tác dụng phụ như vậy có thể xảy ra ngay khi người dùng chạy `help` hoặc lệnh chỉ cần kiểm tra cấu hình. Hãy đưa chúng vào task phù hợp và khai báo đầu vào/đầu ra khi có thể.

Khi cần cấu hình task chuẩn do plugin cung cấp, ưu tiên API như `tasks.named('test', Test) { ... }`. Khi tạo task mới, ưu tiên `tasks.register`. Cách làm này phù hợp với cơ chế cấu hình theo nhu cầu; dùng API cấu hình háo hức không cần thiết có thể làm build lớn chậm.

## 7. Từ yêu cầu `makeReport` đến task graph

Người dùng chỉ yêu cầu `makeReport`. Vì task này khai báo:

```groovy
dependsOn(tasks.named('prepareData'))
```

Gradle đưa task phụ thuộc vào kế hoạch. Hình dung:

```text
Yêu cầu trực tiếp: makeReport
          |
          v
Task graph:
:prepareData ---> :makeReport
                 (phải đi sau prepareData)
```

Những điều cần phân biệt:

| Quan hệ trong Gradle | Có tác dụng gì? | Tự đưa task còn lại vào kế hoạch? |
| --- | --- | --- |
| `dependsOn(x)` | Task đang xét phụ thuộc việc xử lý `x` trước | Có |
| `mustRunAfter(x)` | Nếu cả hai được chọn, task đang xét phải chạy sau `x` | Không |
| `shouldRunAfter(x)` | Ưu tiên thứ tự nếu việc lập lịch cho phép | Không |
| `finalizedBy(x)` | Đăng ký task kết thúc/dọn dẹp sau task được chỉ định | Có, theo cơ chế finalizer |
| `onlyIf { ... }` | Điều kiện để chạy action của task | Không tạo quan hệ phụ thuộc |

**`dependsOn` biểu diễn sự cần thiết, không tự truyền dữ liệu.** Nếu một task sinh file cho task khác, task tiêu thụ còn cần khai báo đúng file đầu vào, hoặc kết nối qua provider/output của task sinh để Gradle hiểu luồng dữ liệu và kiểm tra đầu vào/đầu ra chính xác.

Hai task không có ràng buộc phụ thuộc/thứ tự có thể được xử lý theo thứ tự khác, nhất là khi cấu hình build cho phép chạy song song. Đừng dựa vào thứ tự xuất hiện trong file hoặc thứ tự một lần chạy tình cờ.

Một task graph hợp lệ phải tránh vòng phụ thuộc. Nếu A cần B, B cần C, nhưng C lại cần A, Gradle không thể lập một thứ tự hợp lệ và sẽ báo lỗi thay vì thực thi chu trình đó.

## 8. Quan sát task graph mà chưa chạy hành động với `--dry-run`

Chạy:

```bash
./gradlew --no-configuration-cache --console=plain makeReport --dry-run
```

Thông thường các dòng đáng quan sát gồm:

```text
[INIT] settings.gradle được đánh giá
[CONFIG] build.gradle được đánh giá
:prepareData SKIPPED
:makeReport SKIPPED
```

Hai dòng task có thể xuất hiện kèm log xây dựng khác. Điều quan trọng là **không có** `[EXEC] prepareData` hoặc `[EXEC] makeReport`. Với `--dry-run`, Gradle lập kế hoạch và hiển thị task nhưng **không chạy action của task**.

Ở đây, chữ `SKIPPED` là hậu quả của **chế độ dry-run**. Nó không chứng minh task đã cập nhật, thiếu đầu vào hay có điều kiện `onlyIf` trả về `false`. Muốn chẩn đoán tại sao một task được bỏ qua trong lần chạy thật, cần bỏ `--dry-run` và xem kết quả thực tế.

So sánh ba thử nghiệm:

| Lệnh | Có đánh giá settings/build script theo chế độ mẫu? | Có chạy action hai task tự tạo? |
| --- | --- | --- |
| `./gradlew -q help --no-configuration-cache` | Có | Không |
| `./gradlew makeReport --dry-run --no-configuration-cache` | Có | Không |
| `./gradlew -q makeReport --no-configuration-cache` | Có | Có, lần lượt theo phụ thuộc |

Để không bị ảnh hưởng bởi cache cấu hình, các lệnh trong bảng cố ý tắt configuration cache. Đầu ra hành động trong ví dụ có thể lặp lại vì hai task `doLast` chỉ in thông báo và **không khai báo đầu ra**, nên không có output để Gradle kết luận là up-to-date theo cơ chế kiểm tra đầu vào/đầu ra thông thường.

## 9. Theo dõi execution: task action, trạng thái và nơi tìm output

Khi Gradle đã có kế hoạch, nó xử lý những task được chọn theo ràng buộc. Tuy nhiên, “task có mặt trong graph” và “task thực sự chạy action” không hoàn toàn giống nhau.

Các trạng thái thường gặp:

| Trạng thái hiển thị | Ý nghĩa thường gặp |
| --- | --- |
| Không có nhãn bỏ qua đặc biệt và task chạy action | Gradle đã thực hiện công việc của task |
| `UP-TO-DATE` | Gradle xác định output hiện tại phù hợp với trạng thái đầu vào/đầu ra theo thông tin task đã khai báo |
| `FROM-CACHE` | Gradle khôi phục output từ build cache cho task có thể cache theo điều kiện phù hợp |
| `NO-SOURCE` | Task không có nguồn tương ứng để xử lý |
| `SKIPPED` | Task bị bỏ qua vì một điều kiện/cơ chế tương ứng; với `--dry-run`, mọi action dự kiến đều bị bỏ qua |
| `FAILED` | Task hoặc bước xử lý thất bại |

Các trạng thái cụ thể tùy task, plugin và cấu hình. Một task không có nguồn Java có thể báo `NO-SOURCE` ở `compileJava`, trong khi task khác vẫn có thể thành công. `UP-TO-DATE` không có nghĩa Gradle đã bỏ qua toàn bộ build; task vẫn thuộc kế hoạch nhưng không cần thực hiện action tốn kém.

**Một số cơ chế dễ nhầm:**

- **Up-to-date check:** Dựa trên dữ liệu đầu vào/đầu ra được khai báo và trạng thái đã ghi nhận để quyết định task có cần chạy lại.
- **Build cache:** Lưu/khôi phục output của task có thể cache. Chỉ khai báo output không đảm bảo task tự động cache được.
- **Configuration cache:** Lưu kết quả cấu hình để lần chạy sau có thể tái sử dụng cấu hình và kế hoạch task, giảm việc đánh giá script. Khi cache trúng, dấu `[INIT]`/`[CONFIG]` dùng trong ví dụ có thể không xuất hiện như ở lần chạy mới.
- **Gradle Daemon:** Tiến trình Gradle sống lâu hơn một lệnh, giúp giảm chi phí khởi động. Nó không làm cho tất cả task của lệnh sau được coi là đã chạy.

Vì configuration cache có thể bỏ qua việc đánh giá lại script, khi mục tiêu là **học trình tự giai đoạn**, dùng `--no-configuration-cache` như trong ví dụ. Khi mục tiêu là **đo hiệu năng thực tế**, hãy đo với cấu hình cache của dự án chứ không mặc nhiên tắt mọi tính năng tối ưu.

## 10. Đi theo lệnh `build` thực tế của Java plugin

Ví dụ nhỏ ở trên có `makeReport` và `prepareData` để dễ thấy thứ tự. Với một project áp dụng Java plugin:

```groovy
// build.gradle - một ví dụ riêng, tối giản cho project Java
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}
```

Một file Java chạy được dưới `src/main/java/demo/Hello.java`:

```java
package demo;

public final class Hello {
    private Hello() {
    }

    public static void main(String[] args) {
        System.out.println("Chào từ Gradle");
    }
}
```

Trong project Java mới với `settings.gradle` đặt tên root project, dùng một JDK 17 phù hợp và Wrapper tương thích, chạy:

```bash
./gradlew --no-configuration-cache --console=plain build --dry-run
```

Các task **thường có thể xuất hiện** theo cấu hình mặc định của Java plugin gồm `compileJava`, `processResources`, `classes`, `jar`, `assemble`, `compileTestJava`, `processTestResources`, `testClasses`, `test`, `check` và `build`. Không nên coi thứ tự hiển thị là cố định cho mọi dự án: thêm plugin, dependency, task mới, source set mới hoặc thay đổi cấu hình có thể đổi graph.

Mô hình trách nhiệm:

```text
                             :build
                              /   \
                             /     \
                     :assemble     :check
                         |            |
                        :jar         :test
                         |            |
                      :classes    :testClasses
                         |            |
                compileJava /     compileTestJava /
                processResources  processTestResources
```

Đồ thị trên là **sơ đồ giản lược** giúp đọc vai trò task. Một số quan hệ là do output/classpath gắn kết, một số task có thể là `NO-SOURCE` khi không có Java test hoặc resource, và còn có các phụ thuộc khác không thể hiện trong sơ đồ.

Với file `Hello.java` của ví dụ, `compileJava` tạo bytecode tương ứng trong `build/classes/java/main` và `jar` thường tạo JAR dưới `build/libs`. Không có lớp test thì `compileTestJava` hoặc `test` có thể không có nguồn để xử lý; điều đó không phải là lỗi. Để chạy chương trình bằng `java -cp` hoặc qua plugin `application` cần cấu hình chạy phù hợp; task `build` của Java plugin chủ yếu làm các việc kiểm tra và đóng gói, không mặc định gọi `main` của `Hello`.

Nếu muốn xem rõ task thực sự làm gì:

```bash
./gradlew --no-configuration-cache --console=plain --info build
```

Log `--info` có thể cung cấp lý do task được chạy/bỏ qua, thông tin xử lý nguồn, dependency và đường dẫn. Đây là quan sát có ích hơn việc khẳng định rằng tất cả task đều chạy action ở mỗi lần `build`.

## 11. Cách đọc log đúng trình tự

Khi cần điều tra một build có nhiều task, nên thực hiện lần lượt:

**Bước 1 — ghi rõ chính xác lệnh và project.** Kiểm tra đang ở đúng thư mục build, dùng Wrapper nào, yêu cầu `build` hay `:service:build`, có thêm `--offline`, `--parallel` hoặc `--configuration-cache` hay không.

**Bước 2 — kiểm tra settings và cấu hình.** Nếu lỗi nhắc đến `settings.gradle`, plugin resolution hoặc build script, ưu tiên điều tra trước khi chạm vào Java source. Một lỗi đánh giá script có thể xảy ra dù bạn chỉ chạy `help`.

**Bước 3 — xem danh sách task/quan hệ.** Các lệnh:

```bash
./gradlew --console=plain tasks --all
./gradlew --console=plain help --task build
./gradlew --console=plain build --dry-run
```

`tasks --all` giúp tìm tên task; `help --task` hiển thị thông tin một task; `--dry-run` quan sát kế hoạch mà không chạy hành động.

**Bước 4 — chạy thật với mức log phù hợp.**

```bash
./gradlew --console=plain --info build
```

`--console=plain` giúp log dễ lưu/so sánh, `--info` bổ sung dữ liệu chẩn đoán. Thông tin cụ thể và thứ tự log phụ thuộc phiên bản Gradle, plugin, môi trường và khả năng chạy song song.

**Bước 5 — đối chiếu output.** Với Java plugin, kiểm tra `build/classes`, `build/resources`, `build/libs`, `build/reports/tests` và `build/test-results/test` tương ứng với những task đã chạy. Chỉ thấy dòng `:jar` thành công chưa chứng minh đã chạy test; hãy đọc mục tiêu, task graph và kết quả của `test`.

**Bước 6 — phân loại lỗi theo giai đoạn.** Đọc thông báo ở nơi Gradle chỉ ra file, dòng, task hoặc nguyên nhân. Nếu cần stack trace để biết điểm phát sinh:

```bash
./gradlew --console=plain --stacktrace build
```

Không có quy tắc cố định rằng dòng cuối cùng của log là nguyên nhân gốc. Lỗi thường có khối `* What went wrong:` và phần chỉ ra task hoặc script liên quan; stack trace giúp đào sâu sau khi xác định phần bị lỗi.

## 12. Phân loại một lần thất bại theo vòng đời

| Dấu hiệu | Nên nghĩ đến | Kiểm tra trước |
| --- | --- | --- |
| Wrapper không khởi động được hoặc không tìm được Java | Chuẩn bị môi trường trước vòng đời project | JDK, quyền chạy script, cấu hình Wrapper |
| Lỗi cú pháp hoặc đường dẫn ở `settings.gradle` | Initialization | File settings và khai báo project |
| Không áp dụng được plugin hoặc `build.gradle` báo lỗi khi đánh giá | Configuration hoặc giải quyết plugin/dependency liên quan | Vị trí khai báo, id/version plugin, repository |
| Không tìm thấy task `foo` | Chọn task/mô hình project | Tên task, plugin, đúng đường dẫn project, `tasks --all` |
| `Circular dependency between ...` | Xây dựng quan hệ task | Vòng `dependsOn` hoặc phụ thuộc sinh ra bởi cấu hình |
| `Execution failed for task ':compileJava'` | Execution | Đầu vào Java, toolchain, lỗi trình biên dịch |
| `Execution failed for task ':test'` | Execution | Báo cáo kiểm thử, assert, classpath test |
| `:compileJava NO-SOURCE` | Không có nguồn cho task tương ứng | Kiểm tra `src/main/java` và `sourceSets` nếu kỳ vọng có mã |
| `:jar UP-TO-DATE` | Output hiện tại vẫn phù hợp | Đầu vào/đầu ra và trạng thái task, không mặc định coi là lỗi |

**Đừng nhầm lỗi từ một task với lỗi của Gradle nói chung.** Gradle có thể khởi tạo và cấu hình thành công rồi một test cụ thể thất bại; cách sửa khác hẳn tình huống `settings.gradle` không được đọc thành công.

Một lệnh thất bại có thể để lại một phần output của những task đã chạy trước đó. Vì vậy **file xuất hiện trong `build` không chứng minh toàn bộ build thành công**. Hãy dựa vào kết quả cuối cùng của lệnh, exit code và báo cáo task.

## 13. Vì sao log giữa các lần chạy có thể khác nhau?

Có ít nhất năm lý do đáng nhớ:

1. **Task graph khác nhau.** `help`, `test` và `build` chọn các mục tiêu khác nhau. Các project con và plugin cũng thay đổi đồ thị.
2. **Trạng thái đầu vào/đầu ra khác nhau.** Sau lần build đầu tiên, một số task có thể `UP-TO-DATE`.
3. **Cache khác nhau.** Build cache có thể tạo `FROM-CACHE`; configuration cache có thể tránh đánh giá lại nhiều script và thay đổi các dấu vết cấu hình.
4. **Môi trường khác nhau.** JVM, hệ điều hành, quyền truy cập, plugin, dependency hoặc kết nối mạng có thể gây log khác nhau.
5. **Thực thi song song.** Khi Gradle được cấu hình để chạy các task độc lập song song, thứ tự các dòng log của các task đó không nhất thiết giống mỗi lần. Quan hệ `dependsOn` vẫn phải được tôn trọng.

Vì vậy, **đừng so sánh log như một kịch bản văn bản bất biến**. Hãy kiểm tra các quan hệ không được phép thay đổi: task phụ thuộc phải được xử lý trước task tiêu thụ; cấu hình cần thiết được thiết lập; task action chỉ chạy khi được chọn và không bị bỏ qua; đầu ra và trạng thái cuối khớp với yêu cầu.

Để nghiên cứu hiệu năng, ngoài mức log có thể dùng `--profile` nếu phiên bản Gradle hỗ trợ nhằm tạo báo cáo cục bộ ở vùng báo cáo của `build`. Nhưng thời gian một lệnh chịu ảnh hưởng của cả chi phí khởi động, cấu hình, xử lý dependency và thực thi task. Không nên kết luận “task X chậm” chỉ từ tổng thời gian `BUILD SUCCESSFUL`.

## 14. Những cạm bẫy khi quan sát và thiết kế build

**Cạm bẫy 1: nhầm `println` trong build script với action task.** `println` cấp cao nhất thuộc configuration; `println` bên trong `doLast` thuộc action khi task chạy. Nếu chỉ thấy dòng `[CONFIG]` sau lệnh `help`, đó là hành vi đúng của ví dụ.

**Cạm bẫy 2: viết logic tạo file ngay lúc cấu hình.** Thao tác này có thể xảy ra khi chỉ liệt kê task, gây tốn thời gian hoặc làm biến đổi dữ liệu ngoài mong muốn. Đưa công việc thực tế vào task và khai báo đầu vào/đầu ra.

**Cạm bẫy 3: thay `dependsOn` bằng `mustRunAfter`.** `mustRunAfter` chỉ áp dụng thứ tự khi cả hai task đã nằm trong kế hoạch; nó không tự chọn task cần thiết. Nếu `makeReport` thật sự cần dữ liệu do `prepareData` tạo ra, sử dụng `dependsOn` hoặc quan hệ provider/output phù hợp.

**Cạm bẫy 4: kết luận `SKIPPED` trong `--dry-run` nghĩa là up-to-date.** Khi dry-run, task action được bỏ qua có chủ đích. Cần chạy thật mới phân biệt được `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` hay điều kiện bỏ qua.

**Cạm bẫy 5: thấy kết quả build thành công và nghĩ mọi task đều chạy action.** Build có thể thành công với nhiều task đã được bỏ qua có chủ đích. Điều cần biết là mục tiêu cuối cùng đã được thỏa mãn, chứ không phải số lượng task chạy lại.

**Cạm bẫy 6: tin rằng configuration luôn thực hiện lại mọi script.** Với configuration cache tương thích và được bật, Gradle có thể tái sử dụng cấu hình trước đó; lúc ấy ví dụ in dấu giai đoạn cấp script không còn phản ánh đầy đủ những công việc Gradle tái sử dụng. Khi học hoặc chẩn đoán, hãy nêu rõ cache đang bật/tắt.

**Cạm bẫy 7: dựa vào thứ tự khai báo task.** Gradle lập lịch theo ràng buộc; những task độc lập không có thứ tự được bảo đảm. Để chứng minh thứ tự, hãy chỉ ra cạnh phụ thuộc hoặc ràng buộc thứ tự cụ thể.

## 15. Thực hành tự xác minh từng giai đoạn

Giữ nguyên hai file của mục 4 và thực hiện các thí nghiệm:

### Thí nghiệm A — so sánh cấu hình và thực thi

Chạy:

```bash
./gradlew --no-configuration-cache --console=plain -q help
./gradlew --no-configuration-cache --console=plain -q makeReport
```

Trả lời: vì sao cả hai lệnh đều có thể in `[INIT]`/`[CONFIG]`, nhưng chỉ lệnh thứ hai in hai dòng `[EXEC]`? Đáp án: Gradle cần đánh giá cấu hình để xác định mô hình build; task action chỉ chạy với task thuộc kế hoạch thực thi.

### Thí nghiệm B — kiểm tra task graph

Chạy:

```bash
./gradlew --no-configuration-cache --console=plain makeReport --dry-run
./gradlew --no-configuration-cache --console=plain prepareData --dry-run
```

Dự đoán: yêu cầu `makeReport` kéo theo cả `prepareData`; yêu cầu riêng `prepareData` không kéo theo `makeReport`. Lệnh `--dry-run` không chạy các dòng `doLast`.

### Thí nghiệm C — đổi quan hệ phụ thuộc

Trong `build.gradle`, thử xóa riêng dòng `dependsOn(tasks.named('prepareData'))` rồi chạy lại lệnh dry-run cho `makeReport`. Khi không còn phụ thuộc, Gradle không có lý do chọn `prepareData` cho yêu cầu đó. Khôi phục dòng `dependsOn` để giữ ý nghĩa đúng của bài thực hành.

Đây chỉ là một ví dụ giả lập hai task in thông báo. Trong dự án thật, xóa cạnh phụ thuộc mà task đang cần có thể tạo kết quả sai; cần xác định quan hệ đầu vào/đầu ra trước khi thay đổi.

### Thí nghiệm D — quan sát công việc bị bỏ qua

Chuyển sang dự án Java ở mục 10, chạy hai lần:

```bash
./gradlew --no-configuration-cache --console=plain build
./gradlew --no-configuration-cache --console=plain build
```

Quan sát trạng thái task. Nếu input và output không đổi, một số task có thể báo `UP-TO-DATE`; nếu không có thư mục/file test, một số task liên quan test có thể báo `NO-SOURCE`. Đừng coi các nhãn này là nguyên nhân thất bại khi lệnh cuối cùng báo `BUILD SUCCESSFUL`.

### Thí nghiệm E — tìm điểm thất bại

Tạo lỗi cú pháp có chủ ý trong bản sao của `build.gradle`, thử `./gradlew help --stacktrace` để thấy cấu hình đã thất bại trước task action. Sau đó sửa cú pháp và đặt một hành động task ném lỗi để so sánh thông báo `Execution failed for task ...`. Thí nghiệm trên bản sao giúp tránh ảnh hưởng build đang dùng.

## 16. Câu hỏi tự kiểm tra

1. Khi chạy `./gradlew build`, Wrapper xử lý phần nào trước khi Gradle đánh giá settings?
2. `settings.gradle` thường đóng vai trò gì trong initialization?
3. Vì sao `println` cấp cao nhất trong `build.gradle` có thể chạy khi chỉ dùng `help`?
4. `tasks.register(...)` và `doLast { ... }` khác nhau ở thời điểm có tác dụng như thế nào?
5. Task graph của `makeReport` gồm những task nào, và vì sao?
6. Có thể nhìn thấy task trong `--dry-run` mà không có action nào được chạy không?
7. `UP-TO-DATE`, `FROM-CACHE` và `NO-SOURCE` khác nhau ở đâu?
8. Configuration cache ảnh hưởng thế nào đến cách ta theo dấu các dòng log cấp script?
9. Một build nhiều project cần làm gì để chọn task `build` của project `service`?
10. Lỗi ở `settings.gradle` và lỗi trong `:test` thuộc những chặng khác nhau ra sao?

**Ghi nhớ:** Theo dấu một lệnh Gradle theo chuỗi **lệnh gọi → khởi tạo → cấu hình → chọn task/đồ thị phụ thuộc → thực thi → kết quả**. Dấu vết ở settings/build script cho biết Gradle đã tạo mô hình như thế nào; dấu vết task cho biết kế hoạch đã xử lý ra sao. Kết hợp `--dry-run`, `--info`, trạng thái task và file đầu ra sẽ giúp bạn tìm được nguyên nhân của một lần build thay vì chỉ nhìn dòng cuối cùng.