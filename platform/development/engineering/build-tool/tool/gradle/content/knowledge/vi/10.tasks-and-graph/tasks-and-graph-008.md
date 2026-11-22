# Trạng thái SUCCESS, UP-TO-DATE, FROM-CACHE, NO-SOURCE và SKIPPED của task Gradle

## 1. Task xuất hiện trong đồ thị không có nghĩa action luôn chạy

Khi chạy `./gradlew build`, Gradle xác định những task nào cần xử lý, sắp xếp chúng theo quan hệ phụ thuộc, rồi quyết định **có cần chạy hành động của từng task hay không**. Bước quyết định này giúp Gradle không biên dịch lại thứ đã cập nhật, không chạy công việc không có nguồn và có thể tái sử dụng kết quả đã được lưu trong build cache.

Những tên trạng thái thường gặp là:

- **`SUCCESS`:** task hoàn tất công việc thành công trong lần chạy đó.
- **`UP-TO-DATE`:** đầu vào và đầu ra được theo dõi cho biết task không cần thực hiện lại action.
- **`FROM-CACHE`:** Gradle lấy lại output phù hợp từ build cache, thay vì tự thực hiện action tạo output.
- **`NO-SOURCE`:** task được thiết kế để xử lý nguồn nhưng hiện không có nguồn phù hợp.
- **`SKIPPED`:** task không chạy action vì bị vô hiệu hóa, không thỏa điều kiện hoặc bị bỏ qua theo cơ chế khác.

Các giá trị này có thể thấy trong **kết quả task** (`TaskOutcome`) của Gradle TestKit hoặc dưới dạng nhãn trong log dòng lệnh. Cần phân biệt hai cấp độ:

1. **Trạng thái từng task:** cho biết kết quả xử lý riêng của `:compileJava`, `:test`, `:jar`, v.v.
2. **Kết quả cả lần build:** thông báo `BUILD SUCCESSFUL` hay `BUILD FAILED` và mã thoát của tiến trình.

Một build có thể **`BUILD SUCCESSFUL` dù nhiều task `UP-TO-DATE`, `NO-SOURCE` hoặc `SKIPPED`**. Ngược lại, một task `SUCCESS` không chứng minh tất cả task khác đều thành công.

## 2. Bảng so sánh năm trạng thái

| Trạng thái task | Action của task có chạy trong lần này? | Nguyên nhân/điều kiện tiêu biểu | Bằng chứng cần kiểm tra |
| --- | --- | --- | --- |
| `SUCCESS` | Có thể có; task được xử lý thành công, không thuộc các kết quả bỏ qua/cache ở bảng này | Task chạy hành động cần thiết và không thất bại; task vòng đời không có action vẫn có thể hoàn tất thành công | Dòng task không có nhãn bỏ qua, log action nếu có, output/kết quả |
| `UP-TO-DATE` | Không cần chạy lại action | Input/output được khai báo và trạng thái hiện tại khớp với bản Gradle đã theo dõi | Đầu vào không đổi, output còn hợp lệ, log `UP-TO-DATE` |
| `FROM-CACHE` | Không chạy action sinh kết quả; Gradle khôi phục output | Task đủ điều kiện cache, cache được bật và có bản ghi phù hợp | `FROM-CACHE`; output xuất hiện sau khi khôi phục |
| `NO-SOURCE` | Không có action xử lý nguồn phù hợp để chạy | Tập đầu vào có ý nghĩa “nguồn” rỗng, ví dụ task biên dịch Java không có file Java | `NO-SOURCE`; kiểm tra source set và đường dẫn nguồn |
| `SKIPPED` | Thông thường không chạy action bị bỏ qua | `enabled = false`, `onlyIf { false }`, hoặc `--dry-run`; một số cơ chế bỏ qua khác | `SKIPPED`; dùng `--info` và kiểm tra điều kiện thực tế |

Đừng xem bảng này là quy tắc rằng một task muốn có `SUCCESS` thì nhất thiết phải in thông báo hoặc sinh file. **`SUCCESS` là kết quả xử lý**, còn hành động cụ thể phụ thuộc định nghĩa task. Ví dụ task vòng đời `build` có thể chỉ kết nối các task phụ thuộc mà không tự ghi file nào.

Các kết quả khác như `FAILED` cũng tồn tại, nhưng bài này tập trung vào năm trạng thái trên. Khi task thất bại, Gradle có thể thông báo `FAILED` và kết thúc build với lỗi; không nên xếp lỗi đó vào `SKIPPED`.

## 3. Tên `SUCCESS` và dòng `BUILD SUCCESSFUL` rất dễ bị nhầm

Trong đầu ra dòng lệnh Gradle thông thường, một task chạy thành công thường hiển thị dạng:

```text
> Task :writeNote
[ACTION] writeNote
```

**Gradle không nhất thiết in chữ `SUCCESS` bên cạnh task đó.** Với Gradle TestKit, kết quả của nó có thể được biểu diễn bằng giá trị `TaskOutcome.SUCCESS`. Còn ở cuối lệnh:

```text
BUILD SUCCESSFUL in ...
```

là kết quả **của cả build**, không phải nhãn gắn cho một task cụ thể. Thời gian và số lượng task ở phần kết luận tùy môi trường, nên dấu `...` chỉ biểu thị nội dung log thay đổi, không phải output cần khớp từng ký tự.

Ví dụ một build có thể có log được giản lược như sau:

```text
> Task :compileJava UP-TO-DATE
> Task :processResources NO-SOURCE
> Task :classes
> Task :jar UP-TO-DATE
> Task :compileTestJava NO-SOURCE
> Task :test NO-SOURCE
> Task :check
> Task :build

BUILD SUCCESSFUL in ...
```

Đây là **minh họa kết quả có thể xảy ra** trong một project Java không có resource/test và đã biên dịch trước đó; thứ tự hoặc nhãn cụ thể có thể khác theo project/plugin. Kết luận “build thành công” chỉ nói Gradle hoàn tất mục tiêu theo cấu hình đang có. Nếu bạn **kỳ vọng phải có kiểm thử mà `test` báo `NO-SOURCE`**, cần kiểm tra cấu trúc dự án thay vì tự coi đó là bằng chứng kiểm thử đã đạt.

## 4. Đồ thị task và trạng thái task thuộc hai quyết định khác nhau

Trước hết Gradle phải xác định **task nào cần xử lý**. Quan hệ `dependsOn` đưa task phụ thuộc vào kế hoạch; `mustRunAfter` thường chỉ quy định thứ tự khi cả hai task đã nằm trong kế hoạch.

Sau đó Gradle xử lý từng task và xem nó có nên thực hiện action hay có thể bỏ qua/khôi phục output. Tư duy:

```text
Người dùng yêu cầu :build
           |
           v
Lựa chọn task + phân tích quan hệ phụ thuộc
           |
           v
Task graph của lần chạy hiện tại
           |
           +--> :compileJava  ----> có nguồn? input/output đổi?
           |                              |
           |                              +--> SUCCESS / UP-TO-DATE /
           |                                   FROM-CACHE / NO-SOURCE ...
           |
           +--> :test         ----> có test? điều kiện chạy?
                                          |
                                          +--> SUCCESS / NO-SOURCE /
                                               SKIPPED / ...
```

Một task `UP-TO-DATE` **vẫn được chọn và xử lý trong task graph**; chỉ action không cần chạy lại. Một task `SKIPPED` vẫn có thể là task được yêu cầu trực tiếp. Bởi vậy, nhìn thấy tên task trong `--dry-run` không cho biết action đã chạy.

Cần hiểu thêm: Gradle có thể tính trạng thái task bằng kiểm tra đầu vào/đầu ra, điều kiện bỏ qua, dữ liệu cache và chính sách của task. Thứ tự nội bộ giữa các quyết định đó tùy loại task và phiên bản Gradle; không nên học thuộc một chuỗi “luôn kiểm tra cache trước onlyIf” cho mọi task.

## 5. `UP-TO-DATE`: đã có output hợp lệ cho input hiện tại

Gradle có thể bỏ qua hành động khi biết rằng kết quả đang có vẫn phù hợp với những thứ task đã dùng. Muốn điều này hoạt động đáng tin, task nên mô tả đủ:

- **Input:** giá trị hoặc file ảnh hưởng đến kết quả, ví dụ mã nguồn, tùy chọn compiler, nội dung thông điệp, file cấu hình.
- **Output:** file hoặc thư mục mà task tạo ra.
- **Cách Gradle theo dõi:** đặc điểm của input/output và triển khai task; Gradle còn sử dụng thông tin về hành vi/triển khai task khi xác định trạng thái.

Ví dụ một task sinh file:

```groovy
@org.gradle.api.tasks.CacheableTask
abstract class WriteNote extends org.gradle.api.DefaultTask {
    @org.gradle.api.tasks.Input
    abstract org.gradle.api.provider.Property<String> getLineText()

    @org.gradle.api.tasks.OutputFile
    abstract org.gradle.api.file.RegularFileProperty getDestinationFile()

    @org.gradle.api.tasks.TaskAction
    void generate() {
        File target = destinationFile.get().asFile
        target.parentFile.mkdirs()
        target.setText(lineText.get() + '\n', 'UTF-8')
        println '[ACTION] writeNote'
    }
}
```

Đây là **định nghĩa kiểu task bằng Groovy DSL**, chưa phải một project hoàn chỉnh. Khi task được đăng ký với `lineText` và `destinationFile`, Gradle có đủ thông tin cơ bản để nhận diện sự thay đổi input/output. Mục 9 cung cấp toàn bộ project có thể chạy.

Giả sử lần đầu task tạo `build/generated/note.txt`. Lần tiếp theo nếu `lineText` không đổi, output vẫn tồn tại/hợp lệ và không có yếu tố khác khiến task phải chạy lại, Gradle thường hiển thị:

```text
> Task :writeNote UP-TO-DATE
```

Lúc này **không có dòng `[ACTION] writeNote`** vì action ghi file bị bỏ qua. Trạng thái `UP-TO-DATE` **không có nghĩa Gradle chưa khởi động hoặc task không có trong graph**. Gradle vẫn phải xác định task được yêu cầu và đánh giá tính hợp lệ của kết quả.

Nếu đổi `lineText`, sửa/xóa output, hoặc thay đổi nguồn đầu vào được theo dõi, task có thể được thực thi lại.

### 5.1. Tại sao task không có output thường luôn chạy?

Một task chỉ in ra console:

```groovy
tasks.register('alwaysAction') {
    doLast {
        println '[ACTION] alwaysAction'
    }
}
```

không khai báo file output. Vì vậy Gradle thường không có một sản phẩm trên đĩa để dùng cho kiểm tra up-to-date thông thường, và action sẽ được thực hiện khi task được yêu cầu, trừ khi có cơ chế bỏ qua khác. **Đừng tạo output giả chỉ để ép một task in log đạt `UP-TO-DATE`**.

### 5.2. `UP-TO-DATE` không phải xác minh nghiệp vụ

Gradle kiểm tra dựa trên những gì **task đã khai báo và công cụ có thể theo dõi**. Nếu một task đọc thêm file bên ngoài mà không khai báo file đó là input, Gradle có thể bỏ sót thay đổi và báo `UP-TO-DATE` dù dữ liệu thực tế đã đổi.

Do vậy, khi thấy kết quả cũ, hãy kiểm tra input/output và trạng thái ẩn trước khi chỉ dùng `clean` để chữa triệu chứng.

## 6. `FROM-CACHE`: có kết quả phù hợp trong build cache

Khác với `UP-TO-DATE` (dựa trên output hiện có và trạng thái được theo dõi), `FROM-CACHE` có nghĩa Gradle **khôi phục output từ kho cache** của một task đủ điều kiện, dựa trên dấu vết đầu vào/triển khai phù hợp.

Ví dụ trình tự:

```text
Lần 1:
input A -> action sinh output X -> lưu kết quả X vào build cache (nếu đủ điều kiện)

clean:
xóa output X trong thư mục build

Lần 2:
input A giống trước + cache hit -> lấy X từ cache -> không chạy action
                                      |
                                      v
                                  FROM-CACHE
```

Để chuyện này xảy ra, thông thường phải đủ các điều kiện:

1. **Build cache được bật**, ví dụ dùng `--build-cache` hoặc cấu hình tương ứng.
2. **Task cho phép cache output**. Với task tự định nghĩa, thường cần `@CacheableTask` cùng input/output hợp lệ; task chuẩn/plugin có thể có quy tắc cache riêng.
3. **Có bản ghi cache phù hợp** với đầu vào, triển khai task và các yếu tố được Gradle dùng để xác định khóa cache.
4. **Cache có thể truy cập và chính sách cho phép sử dụng**, output có thể khôi phục an toàn.

Một ví dụ dòng log là:

```text
> Task :writeNote FROM-CACHE
```

Dòng `[ACTION] writeNote` không xuất hiện trong lần cache hit vì action tạo file không chạy. Tuy nhiên, **`FROM-CACHE` không phải kết quả bắt buộc chỉ vì ta chạy `--build-cache`**. Một cache miss, thay đổi input, task không đủ điều kiện hoặc chính sách không lưu/khôi phục sẽ khiến Gradle xử lý theo cách khác.

### 6.1. Cache output task khác cache dependency và configuration cache

| Cơ chế | Lưu/tránh công việc gì? | Dấu hiệu |
| --- | --- | --- |
| **Up-to-date check** | Tránh chạy lại task khi output hiện tại vẫn phù hợp | `UP-TO-DATE` |
| **Build cache** | Tái sử dụng output task đã được lưu | `FROM-CACHE` nếu cache hit |
| **Dependency cache** | Lưu các artifact/metadata dependency đã tải | Không đồng nghĩa task `FROM-CACHE` |
| **Configuration cache** | Tái sử dụng trạng thái cấu hình/graph tương thích giữa các lần build | Có log riêng, không tự biến task thành `FROM-CACHE` |

`--offline` thường ảnh hưởng việc giải quyết dependency từ nguồn ngoài, **không phải “bật FROM-CACHE”**. `clean` xóa build outputs do task `clean` quản lý, không đồng nghĩa xóa toàn bộ build cache. `--no-build-cache` tắt sử dụng build cache cho lần chạy đó, nhưng up-to-date check vẫn có thể hoạt động.

## 7. `NO-SOURCE`: task được chọn nhưng không có nguồn để xử lý

Nhiều task Gradle như `JavaCompile` có một tập file nguồn. Khi tập này rỗng hoặc không có file phù hợp theo quy tắc của task, Gradle có thể báo `NO-SOURCE`:

```text
> Task :compileTestJava NO-SOURCE
```

Ví dụ project áp dụng Java plugin nhưng **chưa có bất kỳ file `.java` trong `src/test/java`**. Chạy `./gradlew compileTestJava` có thể cho `NO-SOURCE`. Task có tên và có trong kế hoạch, nhưng không có mã Java test để biên dịch.

Các nguồn gây nhầm lẫn:

- Đặt test Java sai thư mục, chẳng hạn `tests/java` thay vì `src/test/java`, rồi tưởng Gradle đã kiểm thử.
- File có phần mở rộng không thuộc nhóm task xử lý.
- `sourceSets` tùy chỉnh làm task nhìn vào source root khác.
- Không áp dụng plugin tạo task phù hợp.
- Một source set thực sự chưa có file nguồn, đây có thể hoàn toàn là trạng thái hợp lệ.

Đặc biệt, **`NO-SOURCE` không phải thất bại tự động**. Nhưng nó cũng **không chứng minh test đã được chạy và đạt**. Nếu yêu cầu của bài là “phải có 20 unit test”, trạng thái `test NO-SOURCE` là tín hiệu cần kiểm tra lại dữ liệu và cấu hình test.

### 7.1. `NO-SOURCE` và `UP-TO-DATE` khác nhau

- `NO-SOURCE`: không có nguồn phù hợp để task xử lý; nhiều task được thiết kế với đầu vào nguồn rỗng sẽ bỏ qua công việc.
- `UP-TO-DATE`: có thể có nguồn và output, nhưng Gradle xác định không cần chạy lại công việc vì trạng thái đã phù hợp.

Hai trạng thái đều có thể không chạy action, nhưng **nguyên nhân khác nhau**. Không kết luận “task `NO-SOURCE` đã biên dịch từ cache”; nó không thực hiện biên dịch vì không có nguồn.

## 8. `SKIPPED`: bỏ qua do điều kiện, vô hiệu hóa hoặc mô phỏng

`SKIPPED` là trạng thái rộng hơn một nguyên nhân duy nhất. Nó thường xuất hiện khi task không được phép/cần thực thi action theo một điều kiện đã khai báo.

Ví dụ task có điều kiện `onlyIf`:

```groovy
tasks.register('conditionalSkip') {
    onlyIf { false }

    doLast {
        println '[ACTION] conditionalSkip'
    }
}
```

Khi yêu cầu task này, Gradle sẽ bỏ qua action vì điều kiện trả về `false`. Một ví dụ khác:

```groovy
tasks.register('disabledExample') {
    enabled = false

    doLast {
        println '[ACTION] disabledExample'
    }
}
```

Task bị vô hiệu hóa nên action cũng không chạy. Hai task có thể được liệt kê trong graph, nhưng thường có nhãn `SKIPPED` trong log.

### 8.1. `onlyIf` khác `dependsOn`

- `dependsOn` quyết định task phụ thuộc nào cần được xử lý trước.
- `onlyIf` quyết định **action của task hiện tại** có được phép chạy hay không.
- Nếu một task phụ thuộc vào task khác bị `SKIPPED`, việc task phụ thuộc được xử lý như thế nào còn phụ thuộc dữ liệu và cấu hình. **Không nên tự giả định output của task bị bỏ qua vẫn tồn tại hoặc hợp lệ.**

Muốn chẩn đoán nguyên nhân `SKIPPED`, dùng `--info` để xem thông tin về điều kiện bỏ qua; đọc `enabled` và `onlyIf` trong script/plugin đang cấu hình task.

### 8.2. `SKIPPED` dưới `--dry-run` cần hiểu riêng

Chạy:

```bash
./gradlew build --dry-run
```

Gradle chọn các task theo kế hoạch nhưng **không thực thi các action của task**. Log dry-run thường đánh dấu các task là `SKIPPED`. Đây là **bỏ qua có chủ đích để mô phỏng**, không có nghĩa điều kiện `onlyIf` sai, không có nguồn hoặc output đã cập nhật.

Ví dụ:

```text
> Task :compileJava SKIPPED
> Task :jar SKIPPED
> Task :build SKIPPED
```

Các dòng trên chỉ là minh họa từ chế độ dry-run. Không dùng chúng làm bằng chứng JAR đã được tạo hoặc mã Java đã biên dịch. Cần chạy thật rồi kiểm tra output và trạng thái tương ứng.

### 8.3. `SKIPPED` và `NO-SOURCE` đều không in action, nhưng lý do khác

`SKIPPED` có thể do quy tắc chủ động như `enabled=false`, `onlyIf=false`. `NO-SOURCE` là kết quả dành cho tình huống nguồn đầu vào rỗng ở một task có cơ chế bỏ qua công việc khi không có nguồn. Cần đọc **loại task**, **đầu vào** và **điều kiện** thay vì suy ra một trạng thái từ trạng thái kia.

## 9. Project Gradle có thể chạy để quan sát cả năm trạng thái

Ta sẽ tạo một project Java 17 đơn giản với **Gradle Groovy DSL** và một task tạo file có thể cache. Ví dụ dùng plugin `java` tích hợp sẵn, không cần thư viện bên ngoài. Nó giúp quan sát:

- Task `writeNote` có input/output khai báo và có `@CacheableTask`.
- Task `alwaysAction` có hành động in console, không có output.
- Task `conditionalSkip` có `onlyIf { false }`.
- Task `disabledExample` có `enabled = false`.
- Task `compileTestJava` không có nguồn test, nên thường `NO-SOURCE`.
- Task `compileJava` có một file Java 17 chạy được.

### 9.1. Cây thư mục đầu vào

```text
task-outcome-lab/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'task-outcome-lab'
```

**File `build.gradle` (toàn bộ):**

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

@CacheableTask
abstract class WriteNote extends DefaultTask {
    @Input
    abstract Property<String> getLineText()

    @OutputFile
    abstract RegularFileProperty getDestinationFile()

    @TaskAction
    void generate() {
        File target = destinationFile.get().asFile
        target.parentFile.mkdirs()
        target.setText(lineText.get() + '\n', 'UTF-8')
        println '[ACTION] writeNote'
    }
}

tasks.register('writeNote', WriteNote) {
    group = 'learning'
    description = 'Tao file co khai bao input/output'
    lineText.set(
        providers.gradleProperty('note')
            .orElse('Gradle task outcomes')
    )
    destinationFile.set(
        layout.buildDirectory.file('generated/note.txt')
    )
}

tasks.register('alwaysAction') {
    group = 'learning'
    doLast {
        println '[ACTION] alwaysAction'
    }
}

tasks.register('conditionalSkip') {
    group = 'learning'
    onlyIf { false }
    doLast {
        println '[ACTION] conditionalSkip'
    }
}

tasks.register('disabledExample') {
    group = 'learning'
    enabled = false
    doLast {
        println '[ACTION] disabledExample'
    }
}
```

**File `src/main/java/demo/Main.java`:**

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Java 17 OK");
    }
}
```

Yêu cầu môi trường: Có **Gradle hỗ trợ JDK 17**, và JDK 17 phù hợp đã cài hoặc đã cấu hình cơ chế cung cấp Java toolchain. Với dự án đã có Gradle Wrapper, sử dụng Wrapper của dự án. Nếu đây là thư mục mới chưa có Wrapper, trước tiên phải có một bản Gradle tương thích được cài trên máy để chạy:

```bash
gradle wrapper
```

Sau khi tạo Wrapper, trên Linux/macOS chạy lệnh bằng `./gradlew`; trên Windows PowerShell thay tiền tố bằng `.\gradlew.bat`. Các ví dụ lệnh sau viết theo Linux/macOS để dễ đọc; tùy chọn và tên task giữ nguyên trên Windows.

### 9.2. `SUCCESS`: task chạy action thành công

Bắt đầu với một task không khai báo output:

```bash
./gradlew --console=plain --no-build-cache alwaysAction
```

Trong log sẽ có các dòng từ task:

```text
> Task :alwaysAction
[ACTION] alwaysAction
```

Nếu không có lỗi khác, Gradle kết luận `BUILD SUCCESSFUL`. Trong cách phân loại `TaskOutcome` của TestKit, task được xử lý thành công kiểu này thường có outcome `SUCCESS`. Chữ `SUCCESS` có thể không xuất hiện ngay sau tên task ở dòng lệnh.

Chạy lệnh này thêm lần nữa vẫn thường in `[ACTION] alwaysAction`, vì task không có đầu ra để đánh giá up-to-date theo cơ chế thông thường.

### 9.3. `UP-TO-DATE`: chạy task tạo file hai lần

Lần đầu, bảo đảm không dùng build cache để phân biệt rõ:

```bash
./gradlew --console=plain --no-build-cache writeNote
```

Trong một project mới chưa có output, log đáng chú ý là:

```text
> Task :writeNote
[ACTION] writeNote
```

Task tạo file `build/generated/note.txt` chứa:

```text
Gradle task outcomes
```

File thực tế có thêm ký tự xuống dòng cuối do action dùng `'\n'`.

Chạy **lần thứ hai** với cùng lệnh và không sửa input/output:

```bash
./gradlew --console=plain --no-build-cache writeNote
```

Trạng thái dự kiến:

```text
> Task :writeNote UP-TO-DATE
```

Không có dòng `[ACTION] writeNote` vì không cần ghi file lần nữa. Thay đổi input:

```bash
./gradlew --console=plain --no-build-cache writeNote -Pnote=Changed
```

Lần này action thường chạy lại, cập nhật file thành chuỗi `Changed` kèm xuống dòng. Điều đó chứng minh `@Input` đã đưa giá trị `lineText` vào tính toán trạng thái task.

### 9.4. `NO-SOURCE`: không có Java test

Ví dụ chỉ tạo `src/main/java/demo/Main.java`; **không tạo `src/test/java`**. Chạy:

```bash
./gradlew --console=plain --no-build-cache compileTestJava
```

Với Java plugin và source set mặc định, dòng đáng quan sát thường là:

```text
> Task :compileTestJava NO-SOURCE
```

Gradle vẫn có thể xử lý các task phụ thuộc trước đó, nên không nên coi đây là toàn bộ output. Task `compileTestJava` không có file Java test để biên dịch. Nếu sau này tạo `src/test/java/demo/MainTest.java` hợp lệ, task có nguồn và trạng thái có thể thay đổi; lúc đó cần thư viện/framework nếu test sử dụng API như JUnit.

Để kiểm tra mã chính:

```bash
./gradlew --console=plain --no-build-cache compileJava
java -cp build/classes/java/main demo.Main
```

Dòng do chương trình Java in chính xác:

```text
Java 17 OK
```

Lệnh `compileJava` tạo `Main.class` nhưng **không tự chạy phương thức `main`**; kết quả trên đến từ lệnh `java -cp ...`.

### 9.5. `SKIPPED`: điều kiện sai và task bị vô hiệu hóa

Chạy:

```bash
./gradlew --console=plain --no-build-cache conditionalSkip disabledExample
```

Hai task có thể được hiển thị như sau:

```text
> Task :conditionalSkip SKIPPED
> Task :disabledExample SKIPPED
```

Không có dòng `[ACTION] conditionalSkip` hoặc `[ACTION] disabledExample`. Trong script, `conditionalSkip` có điều kiện `false` và `disabledExample` được đặt `enabled = false`.

Đây là lý do bỏ qua thật trong lần chạy này. Khi chỉ dùng `--dry-run`, nhãn `SKIPPED` lại có nghĩa mô phỏng; phải phân biệt theo tham số và ngữ cảnh.

### 9.6. `FROM-CACHE`: thử khôi phục output qua build cache

Task `WriteNote` có `@CacheableTask`, input/output đã khai báo và action tạo nội dung xác định. Thử cùng một giá trị `note` hai lần, xóa output giữa hai lần:

```bash
./gradlew --console=plain --build-cache clean writeNote -Pnote=CacheDemo
./gradlew --console=plain --build-cache clean writeNote -Pnote=CacheDemo
```

Sau lần đầu, nếu task được thực thi và cho phép lưu cache, Gradle có thể giữ một bản output. Lệnh `clean` trong lần thứ hai xóa output hiện có. Khi cache có bản ghi phù hợp và chính sách cache cho phép, lần thứ hai có thể hiển thị:

```text
> Task :writeNote FROM-CACHE
```

Trong lần cache hit, file `build/generated/note.txt` được khôi phục mà action `generate` không chạy, nên sẽ không có `[ACTION] writeNote`.

**Không bảo đảm tuyệt đối** sẽ thấy `FROM-CACHE` trên mọi máy: cache có thể đã bị dọn, bị tắt bằng cấu hình khác, cache key thay đổi, task không đủ điều kiện do môi trường hoặc có nguyên nhân khiến Gradle không khôi phục kết quả. Nếu không thấy trạng thái này, dùng `--info` để tìm lý do thay vì tự kết luận build sai.

Để so sánh, `--no-build-cache` tắt việc dùng build cache trong lệnh. Khi bạn xóa output bằng `clean` rồi chạy `writeNote --no-build-cache`, task thường phải sinh lại file, trừ các cơ chế bỏ qua khác. Khi không xóa output và input không đổi, task vẫn có thể `UP-TO-DATE` dù build cache bị tắt.

### 9.7. `--dry-run` tạo trạng thái `SKIPPED` mô phỏng

Chạy:

```bash
./gradlew --console=plain --dry-run writeNote alwaysAction conditionalSkip
```

Gradle trình bày những task dự kiến xử lý nhưng không thực thi action của chúng. Các dòng có nhãn `SKIPPED` trong trường hợp này **không phải bằng chứng** rằng `writeNote` thực sự bị điều kiện sai hay đã tạo file.

Lúc muốn chắc chắn nội dung file tồn tại và đúng, hãy bỏ `--dry-run`, chạy task thật rồi mở `build/generated/note.txt`.

## 10. Đọc log: nhận diện trạng thái và lý do

Dùng những lệnh sau trong project thực hành:

```bash
./gradlew --console=plain tasks --all
./gradlew --console=plain --dry-run build
./gradlew --console=plain --info writeNote
./gradlew --console=plain --info conditionalSkip
./gradlew --console=plain --build-cache --info clean writeNote
```

Các mục đích chính:

- **`tasks --all`:** tìm task đã được plugin hoặc build script đăng ký.
- **`--dry-run`:** xem kế hoạch task, không kiểm chứng output hay trạng thái thực thi thật.
- **`--info`:** xem thêm thông tin chẩn đoán về đầu vào, trạng thái task, cache và điều kiện bỏ qua. Không dựa vào một câu log cố định cho mọi phiên bản Gradle.
- **`--build-cache`:** bật cơ chế tái sử dụng output cache cho task đủ điều kiện; không ép mọi task `FROM-CACHE`.
- **`--console=plain`:** in log dạng văn bản ổn định hơn khi thu thập hoặc so sánh.

Với lỗi thực thi, chạy `./gradlew --stacktrace ...` khi cần xem dấu vết ngăn xếp. Khi build báo lỗi, hãy phân biệt `FAILED` ở task với `SKIPPED` ở task khác: không phải mọi task còn lại đều được thực thi sau khi xảy ra lỗi.

### 10.1. Điều gì có thể thay đổi giữa hai lần build?

- Người dùng yêu cầu task khác hoặc thêm plugin, khiến **task graph** khác.
- Đầu vào được sửa hoặc output bị xóa, khiến **up-to-date check** thay đổi.
- Build cache có hoặc thiếu dữ liệu phù hợp, dẫn đến `FROM-CACHE` hoặc phải chạy action.
- Điều kiện `onlyIf`, `enabled` hoặc tùy chọn `--dry-run` thay đổi.
- Source set bị thay đổi, dẫn đến có/không có nguồn Java hoặc resource.
- Tùy chọn cấu hình build, môi trường JDK, dependency và plugin ảnh hưởng cách thực thi.

Do đó không nên so khớp toàn bộ log như một bản văn cố định. Hãy kiểm tra **task nào được chọn, action có chạy không, file đầu ra và nguyên nhân của trạng thái**.

## 11. Nhìn trạng thái qua Gradle TestKit

Gradle TestKit cung cấp kiểu `org.gradle.testkit.runner.TaskOutcome` với các hằng như:

```text
SUCCESS
FAILED
UP_TO_DATE
SKIPPED
FROM_CACHE
NO_SOURCE
```

Lưu ý cách viết hằng trong mã Java/Kotlin: `UP_TO_DATE`, `FROM_CACHE`, `NO_SOURCE` dùng **dấu gạch dưới**. Log dòng lệnh thường dùng `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` với **dấu gạch nối**.

Khi viết kiểm thử plugin Gradle bằng TestKit, ta có thể tra `BuildResult.task(":writeNote")` để lấy kết quả task và so sánh với `TaskOutcome.SUCCESS`, `TaskOutcome.UP_TO_DATE` hoặc `TaskOutcome.FROM_CACHE`. Đây là kiểm tra **hành vi build logic**; nó khác với kiểm thử đơn vị JUnit của lớp Java nằm dưới `src/test/java`.

Ví dụ câu kiểm tra có ngữ cảnh (đoạn mã Groovy minh họa **bên trong một test đã thiết lập GradleRunner và lấy `BuildResult result`**, không phải chương trình độc lập):

```groovy
import org.gradle.testkit.runner.TaskOutcome

assert result.task(':writeNote').outcome == TaskOutcome.UP_TO_DATE
```

Đoạn này chỉ đúng khi test trước đó đã chạy task trong điều kiện đầu vào/output không đổi để tạo `UP_TO_DATE`. Không nên copy một câu assert này vào build script hoặc giả định lần chạy đầu tiên sẽ cho `UP_TO_DATE`.

## 12. Trạng thái không tự bảo đảm đúng yêu cầu nghiệp vụ

Trong quá trình làm việc thực tế, trạng thái task có thể giúp đánh giá hiệu năng, nhưng cần kiểm tra cả chất lượng kết quả:

| Điều bạn nhìn thấy | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| `BUILD SUCCESSFUL` | Gradle hoàn tất các mục tiêu được cấu hình cho lệnh | Tất cả bài kiểm thử mong muốn đều tồn tại và đã chạy |
| `:test NO-SOURCE` | Task test không có nguồn kiểm thử phù hợp theo cách nó được cấu hình | Ứng dụng đã qua kiểm thử |
| `:test SKIPPED` | Action test bị bỏ qua trong lần chạy đó | Các assertion đều đạt |
| `:compileJava UP-TO-DATE` | Gradle không cần thực hiện lại action biên dịch theo trạng thái theo dõi | Không còn lỗi logic trong chương trình |
| `:jar FROM-CACHE` | Output JAR phù hợp được khôi phục từ cache | JAR đã được tái biên dịch trong lần chạy hiện tại |
| `:writeNote SUCCESS` | Task xử lý thành công lần này | Mọi task khác trong build đã thực thi |

Điểm thiết yếu: Nếu yêu cầu của dự án là “mọi test phải chạy trước release”, người chịu trách nhiệm cần xem **task test có được chọn, có bài test hay không, test report và chính sách build**, chứ không chỉ nhìn `BUILD SUCCESSFUL`.

Với task tự viết, trách nhiệm của tác giả là khai báo input/output đầy đủ và tránh phụ thuộc trạng thái ẩn. Gradle đưa ra trạng thái dựa trên mô hình được cung cấp; nếu mô hình sai, trạng thái có vẻ hợp lệ vẫn có thể che một lỗi thiết kế.

## 13. Lỗi và hiểu nhầm thường gặp

| Hiểu nhầm/triệu chứng | Giải thích đúng | Hướng xử lý |
| --- | --- | --- |
| “`UP-TO-DATE` nghĩa là task chưa được Gradle đụng đến” | Task vẫn được chọn và kiểm tra; chỉ action không phải chạy lại | Xem graph, input/output và trạng thái |
| “`FROM-CACHE` đồng nghĩa lấy dependency từ Maven cache” | `FROM-CACHE` nói đến **output task** từ build cache | Phân biệt build cache với dependency cache |
| “Có `--build-cache` thì task nào cũng `FROM-CACHE`” | Cần task đủ điều kiện và cache hit | Xem `--info`, input/output, cấu hình cache |
| “`NO-SOURCE` nghĩa là compile lỗi” | Không có nguồn thích hợp để xử lý | Kiểm tra `src/main/java`, `src/test/java`, `sourceSets` |
| “`test NO-SOURCE` chứng minh các test đã pass” | Không có test để task thực hiện theo cấu hình hiện tại | Kiểm tra test source, engine, test report |
| “`SKIPPED` luôn là do `onlyIf=false`” | Có thể do `enabled=false` hoặc `--dry-run` và cơ chế khác | Xem điều kiện/tùy chọn và log `--info` |
| “`BUILD SUCCESSFUL` nghĩa là mọi task có `SUCCESS`” | Nhiều task có thể `UP-TO-DATE`, `NO-SOURCE`, `SKIPPED` hoặc `FROM-CACHE` | Đọc trạng thái từng task |
| “Đổi file ngoài task nhưng task vẫn up-to-date là lỗi Gradle” | Task có thể chưa khai báo file ảnh hưởng kết quả làm input | Sửa định nghĩa input/output, tránh trạng thái ẩn |
| “`clean` xóa luôn build cache” | `clean` thường chỉ xóa build outputs của project | Phân biệt output directory với cache Gradle |
| “Task không tạo file vẫn phải up-to-date” | Thiếu output, Gradle thường không có gì để xác nhận đã cập nhật | Chỉ khai báo output nếu task thực sự tạo output |
| “`--rerun-tasks` làm task `SKIPPED` bắt buộc chạy” | Tùy chọn ép chạy lại công việc đủ điều kiện, không gỡ mọi điều kiện bỏ qua hoặc tạo nguồn còn thiếu | Kiểm tra `onlyIf`, `enabled`, source set |
| “`--dry-run` đã kiểm tra kết quả thành công” | Dry-run không thực thi action nên không xác minh output | Chạy thật và đọc artifact/report |

## 14. Thực hành củng cố

**Bài tập 1 — dự đoán hai lần chạy.** Dùng project mục 9, chạy `writeNote` hai lần với `--no-build-cache` và không thay file. Dự đoán lần đầu in `[ACTION] writeNote`, lần sau có thể `UP-TO-DATE`. Giải thích vai trò của `@Input` và `@OutputFile`.

**Bài tập 2 — đổi input.** Chạy `writeNote -Pnote=One` rồi `writeNote -Pnote=Two`. Mở `build/generated/note.txt` sau từng lần. Vì sao không nên chỉ khai báo `destinationFile` mà bỏ `lineText` khỏi input?

**Bài tập 3 — xóa output nhưng giữ cache.** Dùng `--build-cache` hai lần với `clean writeNote -Pnote=Same`, so sánh việc task chạy action và phục hồi output. Nếu không có `FROM-CACHE`, tìm lý do trong `--info`. Giải thích tại sao cùng input **chưa đủ** để bảo đảm cache hit.

**Bài tập 4 — thử `NO-SOURCE`.** Chạy `compileTestJava` khi chưa có file test. Sau đó tạo file Java test hợp lệ dưới `src/test/java/demo` (không nhất thiết dùng JUnit) rồi chạy lại. Quan sát trạng thái thay đổi khi source set có nguồn.

**Bài tập 5 — thử `SKIPPED`.** So sánh `conditionalSkip` và `disabledExample` ở mục 9; cả hai không in action, nhưng điều kiện bỏ qua khác nhau như thế nào? Thử lệnh `--dry-run` và cho biết tại sao nhãn `SKIPPED` khi ấy có ý nghĩa khác.

**Bài tập 6 — task graph và trạng thái.** Chạy `build --dry-run` rồi `build`. Đọc những task nào được lựa chọn, task nào thực thi, task nào bị bỏ qua hoặc không có nguồn. Không suy đoán hiệu quả kiểm thử chỉ từ kết luận `BUILD SUCCESSFUL`.

**Bài tập 7 — sửa mô hình input sai.** Trong bản sao project thực hành, thử bỏ `@Input` khỏi `lineText`. Giải thích vì sao Gradle có thể báo lỗi kiểm tra thuộc tính task chưa được đánh dấu, hoặc không thể theo dõi thay đổi đúng nếu mô hình đầu vào thiếu khai báo. Khôi phục annotation trước khi sử dụng task thật.

### Câu hỏi tự kiểm tra

1. `TaskOutcome.SUCCESS` và thông báo `BUILD SUCCESSFUL` khác nhau ở cấp độ nào?
2. Vì sao một task có mặt trong task graph vẫn có thể `UP-TO-DATE`?
3. Điều kiện nào cần để một task có thể báo `FROM-CACHE`?
4. `--no-build-cache` có tự vô hiệu hóa up-to-date check không?
5. Khi không có file Java test, `compileTestJava` thường báo gì? Có phải lỗi không?
6. `onlyIf { false }`, `enabled = false` và `--dry-run` có điểm chung và khác nhau gì?
7. Vì sao không nên coi `:test NO-SOURCE` là bằng chứng toàn bộ kiểm thử đã qua?
8. Nếu đầu vào của task bị thay đổi nhưng task vẫn `UP-TO-DATE`, nên xem những khai báo nào?
9. Tại sao chạy `clean` không nhất thiết khiến Gradle mất cơ hội `FROM-CACHE`?
10. `UP_TO_DATE` trong Gradle TestKit khác `UP-TO-DATE` trong CLI như thế nào?
11. Với một task chỉ in console và không có output, vì sao không nhất thiết cần cố gắng làm nó được cache?
12. Muốn đánh giá một build thành công có thực sự sẵn sàng phát hành, còn phải kiểm tra điều gì ngoài trạng thái task?

**Ghi nhớ:** `SUCCESS` nói task hoàn tất bình thường; `UP-TO-DATE` nói kết quả hiện tại vẫn hợp lệ; `FROM-CACHE` nói output được khôi phục từ cache; `NO-SOURCE` nói task không có nguồn phù hợp; `SKIPPED` nói action bị bỏ qua bởi một điều kiện/cơ chế. Đọc các trạng thái **trong ngữ cảnh task graph, input/output, cache và yêu cầu kiểm thử thực tế** để phân biệt tối ưu hợp lệ với cấu hình còn thiếu.