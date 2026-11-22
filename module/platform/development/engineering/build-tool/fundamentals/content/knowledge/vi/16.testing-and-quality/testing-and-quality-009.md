# Bỏ qua kiểm thử hoặc bỏ qua lỗi: tác động và phạm vi sử dụng

Trong Gradle, “bỏ qua test” và “bỏ qua lỗi test” là hai hành động khác nhau. Bỏ qua test có nghĩa là một hoặc nhiều test không được thực thi trong lần build đó. Bỏ qua lỗi có nghĩa test vẫn chạy, kết quả vẫn được ghi nhận, nhưng lỗi test không làm build thất bại theo cách thông thường.

Sự khác biệt này ảnh hưởng trực tiếp đến task graph, thời gian build, kết quả báo cáo và độ tin cậy của pipeline. Khi dùng các tùy chọn như `-x test`, `enabled = false`, `onlyIf` hoặc `ignoreFailures = true`, cần hiểu chính xác phạm vi của chúng: một lệnh cục bộ, một task, mọi task kiểm thử trong project, một loại test hay cả pipeline CI.

## 1. Phân biệt các mục tiêu thường bị gọi chung là “skip test”

Có ít nhất bốn mục tiêu khác nhau:

1. Không đưa task kiểm thử vào lần build hiện tại.
2. Để task nằm trong graph nhưng không thực thi action.
3. Chạy test nhưng cho phép build tiếp tục dù test thất bại.
4. Chỉ chạy một tập con test được chọn.

Các mục tiêu này có cách cấu hình và kết quả khác nhau.

| Cách làm | Test có thực thi không? | Build có thể tiếp tục sau test fail? | Phạm vi điển hình |
|---|---:|---:|---|
| `-x test` | Không | Không áp dụng vì task bị loại khỏi graph | Một lần gọi Gradle |
| `enabled = false` | Không | Không áp dụng | Task được cấu hình |
| `onlyIf { ... }` trả về false | Không | Không áp dụng | Task theo điều kiện |
| Test filter như `--tests` | Có, với test được chọn | Mặc định build vẫn fail nếu test được chọn thất bại | Một lần chạy/task |
| `ignoreFailures = true` | Có | Có | Một Test task được cấu hình |
| `--continue` | Task được chọn vẫn chạy theo điều kiện graph | Build cuối cùng vẫn thất bại nếu có task thất bại | Một lần gọi Gradle |

Cần chọn cách phù hợp với mục tiêu. Nếu cần chạy nhanh một phần test, hãy dùng test filter. Nếu cần bỏ qua một task trong một lần gọi, dùng exclusion. Nếu cần giữ báo cáo test nhưng không chặn một bước tiếp theo, `ignoreFailures` có thể phù hợp. Nếu muốn pipeline vẫn ghi nhận thất bại nhưng tiếp tục các task độc lập, xem xét `--continue`.

## 2. Bỏ task khỏi graph bằng -x / --exclude-task

Gradle cung cấp tùy chọn dòng lệnh `-x` hoặc `--exclude-task` để loại task khỏi task graph của lần gọi hiện tại.

Ví dụ:

~~~shell
./gradlew build -x test
~~~

Với build nhiều project, task tên `test` có thể tồn tại ở nhiều project. Cần xem task graph để xác nhận chính xác task nào bị loại trong lệnh đang chạy.

Lệnh này hữu ích khi cần tạm bỏ qua task kiểm thử trong một lần build cục bộ, ví dụ để kiểm tra riêng bước đóng gói trong lúc đang xử lý một lỗi test đã biết.

### Điều gì xảy ra với task graph?

Giả sử task `build` phụ thuộc vào `check`, và `check` phụ thuộc vào `test`:

~~~text
build
  |
  +--> assemble
  |
  +--> check
          |
          +--> test
~~~

Khi gọi `build -x test`, task `test` bị loại khỏi graph của lần chạy đó. Gradle vẫn có thể chạy `build`, `assemble` và `check` nếu các quan hệ còn lại cho phép.

Điều này có nghĩa task tổng hợp `build` có thể hoàn tất thành công dù test không được thực thi. Kết quả đó không chứng minh mã nguồn đã vượt qua kiểm thử; nó chỉ cho biết những task còn lại trong graph đã hoàn tất.

### Dependency của task bị loại thì sao?

Khi một task bị loại khỏi graph, những task chỉ được yêu cầu vì task đó có thể không còn cần chạy. Ví dụ, `testClasses` thường được nối vào `test` để biên dịch test source và xử lý test resources. Nếu không có task nào khác yêu cầu các output này, chúng có thể không được thực thi trong lần build bị loại `test`.

Tuy nhiên, nếu một task khác trong graph cũng cần output của `testClasses`, các task đó vẫn có thể được chọn. Vì vậy, không nên kết luận rằng `-x test` luôn bỏ qua mọi công việc liên quan đến test compilation.

### Exclusion chỉ có hiệu lực cho lần gọi hiện tại

`-x test` không sửa build script hoặc project configuration. Lần chạy sau không có tùy chọn này sẽ dùng graph thông thường.

Đây là ưu điểm khi cần một ngoại lệ tạm thời, nhưng cũng là rủi ro nếu lệnh CI hoặc script dùng chung âm thầm giữ tùy chọn này. Người đọc log cần biết task đã bị loại theo lệnh nào.

### Kiểm tra task graph trước khi chạy

Có thể xem graph dự kiến:

~~~shell
./gradlew build -x test --dry-run
~~~

`--dry-run` giúp quan sát những task Gradle dự kiến thực hiện mà không chạy action thông thường. Dùng nó để xác nhận việc loại task có ảnh hưởng đến các task khác như mong đợi hay không.

Với build nhiều project, hãy kiểm tra task path và output thực tế; không giả định một tên task chung chỉ nhắm vào một project.

## 3. Tắt task bằng enabled = false

Có thể cấu hình task không thực thi bằng thuộc tính `enabled`:

~~~groovy
tasks.named('test', Test) {
    enabled = false
}
~~~

Khi task bị disable, Gradle vẫn nhận diện task trong model/graph nhưng đánh dấu nó không thực thi. Cách này là cấu hình của project, vì vậy có hiệu lực ở mọi lần gọi mà cấu hình đó được áp dụng.

### Khác biệt so với -x

| Đặc điểm | `-x test` | `enabled = false` |
|---|---|---|
| Nơi thiết lập | Dòng lệnh | Build script hoặc plugin |
| Thời hạn | Một lần gọi | Mọi lần build áp dụng cấu hình |
| Task trong graph | Bị loại khỏi graph | Có thể vẫn xuất hiện nhưng bị skip |
| Dependencies | Chỉ chạy nếu còn được task khác yêu cầu | Dependencies của task vẫn có thể chạy |
| Khả năng nhìn thấy trong cấu hình | Nằm trong command invocation | Nằm trong cấu hình project |

Vì task bị disable nhưng vẫn có thể có dependency, những task chuẩn bị đầu vào cho nó có thể vẫn chạy. Ví dụ, `testClasses` có thể được thực hiện trước khi Gradle đánh dấu `test` là `SKIPPED`, tùy graph và cấu hình.

Nếu mục tiêu là tránh toàn bộ công việc chỉ phục vụ test trong một lần gọi, exclusion thường có tác động khác với disable task trong build script. Hãy xem graph để xác nhận.

### Cẩn thận với cấu hình toàn bộ Test task

Có thể viết:

~~~groovy
tasks.withType(Test).configureEach {
    enabled = false
}
~~~

Đoạn này áp dụng cho mọi task thuộc type `Test` trong project hiện tại, có thể gồm `test`, `integrationTest` và các task kiểm thử khác do plugin đăng ký.

Nếu đặt trong convention plugin hoặc cấu hình dùng chung, phạm vi ảnh hưởng có thể rộng hơn dự kiến. Không nên tắt toàn bộ Test task chỉ vì muốn tạm bỏ qua một bộ integration test.

Khi cần giới hạn, cấu hình đúng task:

~~~groovy
tasks.named('integrationTest', Test) {
    enabled = false
}
~~~

Tên task phải khớp với task thực tế mà project đã đăng ký.

## 4. Bỏ qua theo điều kiện bằng onlyIf

`onlyIf` cho phép Gradle quyết định có thực thi task hay không dựa trên một điều kiện. Điều kiện được đánh giá khi task sắp thực thi.

Ví dụ, chỉ chạy integration test khi không có project property yêu cầu bỏ qua:

~~~groovy
def skipIntegrationTests = providers.gradleProperty('skipIntegrationTests')
    .map { it.toBoolean() }
    .getOrElse(false)

tasks.named('integrationTest', Test) {
    onlyIf {
        !skipIntegrationTests
    }
}
~~~

Chạy mặc định:

~~~shell
./gradlew integrationTest
~~~

Yêu cầu bỏ qua:

~~~shell
./gradlew integrationTest -PskipIntegrationTests=true
~~~

Khi property có giá trị `true`, điều kiện trả về false và task `integrationTest` bị skip.

### onlyIf vẫn giữ dependency của task

Điều kiện `onlyIf` quyết định action của chính task có chạy hay không. Các dependency của task có thể đã được đưa vào graph và thực thi trước khi điều kiện được đánh giá.

Ví dụ, `integrationTest` có thể phụ thuộc vào `testClasses`, task chuẩn bị dữ liệu hoặc task tạo fixture. Khi `onlyIf` trả về false, các dependency đó vẫn có thể chạy.

Điểm này quan trọng nếu mục tiêu là tiết kiệm thời gian hoặc tránh một dịch vụ phụ trợ. Chỉ skip action của task không đảm bảo mọi bước chuẩn bị liên quan đều bị loại.

### Điều kiện phải rõ ràng và có thể quan sát

Nếu dùng property để điều khiển skip, tên property nên diễn tả đúng task và mục đích. Tránh một cờ chung như `skipAll` nếu nó có thể bỏ qua nhiều nhóm kiểm thử mà người gọi không nhận ra.

Nên làm rõ trong tài liệu pipeline:

- Property nào có thể bỏ qua task.
- Task nào bị ảnh hưởng.
- Mặc định có chạy test hay không.
- Báo cáo nào vẫn được tạo.
- Pipeline nào được phép dùng cờ này.

Không nên để việc skip phụ thuộc vào một biến môi trường bí mật hoặc giá trị mặc định không được giải thích.

## 5. Chạy test nhưng không làm build thất bại bằng ignoreFailures

`ignoreFailures` là thuộc tính của Gradle `Test` task. Khi đặt thành `true`, Gradle cho phép task kiểm thử hoàn tất mà không làm build thất bại chỉ vì test có kết quả thất bại.

Ví dụ:

~~~groovy
tasks.named('test', Test) {
    ignoreFailures = true
}
~~~

Trong trường hợp này:

- Test vẫn được thực thi.
- Các assertion và test case vẫn được chạy theo cấu hình.
- Kết quả test vẫn được thu thập.
- Báo cáo vẫn có thể hiển thị test thất bại.
- Build có thể tiếp tục và hoàn tất thành công dù có test fail.

Đây không phải cách bỏ qua test. Nó thay đổi cách task xử lý kết quả thất bại.

### Test vẫn chạy và vẫn có bằng chứng thất bại

Giả sử có ba test:

~~~text
OrderServiceTest
  - creates order       PASSED
  - rejects invalid    FAILED
  - calculates total   PASSED
~~~

Với `ignoreFailures = true`, Gradle vẫn chạy test và báo cáo test thất bại. Tuy nhiên, lỗi test không làm task thất bại theo cơ chế mặc định, nên các task phụ thuộc tiếp theo có thể tiếp tục.

Build status xanh trong tình huống này không đồng nghĩa toàn bộ test đều pass. Cần xem report và trạng thái kiểm thử riêng.

### Cấu hình cho một task cụ thể

Nếu chỉ muốn cho phép một task kiểm thử không chặn build:

~~~groovy
tasks.named('integrationTest', Test) {
    ignoreFailures = true
}
~~~

Các task `test` hoặc task kiểm thử khác vẫn giữ hành vi mặc định nếu không được cấu hình.

### Cấu hình cho mọi Test task

~~~groovy
tasks.withType(Test).configureEach {
    ignoreFailures = true
}
~~~

Cấu hình này ảnh hưởng mọi `Test` task trong project. Nó có thể làm unit test, integration test và các test suite khác cùng không chặn build khi có test fail.

Đây là phạm vi rộng và thường không phù hợp làm mặc định của convention plugin dùng chung. Nếu chỉ một bộ test được phép non-blocking, hãy cấu hình đúng task đó.

### ignoreFailures không bỏ qua lỗi compile hoặc lỗi hạ tầng

`ignoreFailures` điều chỉnh việc xử lý kết quả test thất bại của `Test` task. Nó không biến lỗi biên dịch test, lỗi cấu hình build, lỗi resolve dependency hoặc mọi lỗi khởi động worker thành kết quả hợp lệ.

Ví dụ:

- `compileTestJava` thất bại vì lỗi cú pháp: test task không thể chạy bình thường.
- Không resolve được test dependency: build vẫn có thể thất bại.
- Test worker không thể khởi động hoặc process gặp sự cố nghiêm trọng: task có thể vẫn thất bại.
- Assertion trong test thất bại: `ignoreFailures` cho phép build tiếp tục theo cấu hình.

Vì vậy, không dùng thuộc tính này như một cách tổng quát để che mọi lỗi liên quan đến kiểm thử.

## 6. Chỉ chạy một phần test bằng test filtering

Nếu mục tiêu là chạy nhanh một nhóm test cụ thể, thường nên dùng test filtering thay vì bỏ qua cả task.

Ví dụ chạy một class:

~~~shell
./gradlew test --tests "com.example.order.OrderServiceTest"
~~~

Chạy một nhóm package/pattern:

~~~shell
./gradlew test --tests "com.example.order.*"
~~~

Chạy một method:

~~~shell
./gradlew test --tests "com.example.order.OrderServiceTest.rejectsInvalidOrder"
~~~

Tên class/method và pattern phải phù hợp với test engine và cấu trúc project.

Filtering giữ task `test` trong graph và task vẫn thực thi. Gradle chỉ chọn các test khớp với filter. Nếu một test được chọn thất bại, build vẫn thất bại theo mặc định trừ khi có cấu hình `ignoreFailures`.

### Test filter và bỏ qua test khác nhau thế nào?

| Mục tiêu | Cách phù hợp |
|---|---|
| Chỉ chạy một class trong lúc phát triển | `--tests` |
| Chạy toàn bộ unit test | `test` |
| Chạy integration test riêng | Task integration test tương ứng |
| Không thực thi task test trong một lần build | `-x test` |
| Test vẫn chạy nhưng kết quả fail không chặn build | `ignoreFailures = true` |

Filtering hữu ích khi sửa một class và cần feedback nhanh. Trước khi merge hoặc release, pipeline vẫn cần chạy đầy đủ các bộ test bắt buộc theo chính sách repository.

## 7. --continue không phải ignoreFailures

Tùy chọn `--continue` yêu cầu Gradle tiếp tục thực thi các task độc lập có thể chạy sau khi một task thất bại, thay vì dừng toàn bộ build ngay khi gặp lỗi đầu tiên.

Ví dụ:

~~~shell
./gradlew build --continue
~~~

Nếu một task kiểm thử thất bại, Gradle có thể tiếp tục các task khác không phụ thuộc vào task thất bại đó. Tuy nhiên, build cuối cùng vẫn được đánh dấu thất bại nếu có task thất bại.

So sánh:

| Hành vi | `ignoreFailures = true` | `--continue` |
|---|---|---|
| Test task có chạy không? | Có | Có nếu được chọn vào graph |
| Test fail có làm Test task thất bại không? | Không theo cơ chế ignore failure | Có |
| Các task độc lập có thể tiếp tục không? | Có, vì task không làm build dừng do test failure | Có, theo quy tắc continue |
| Build cuối cùng có thể xanh dù test fail không? | Có | Không, nếu task vẫn thất bại |
| Phạm vi | Cấu hình của Test task | Một lần gọi Gradle |

Dùng `--continue` khi cần thu thập nhiều kết quả trong một lượt, ví dụ chạy nhiều nhóm kiểm tra độc lập để có báo cáo đầy đủ. Dùng `ignoreFailures` khi chủ đích là không để kết quả thất bại của một Test task chặn build. Hai lựa chọn có ý nghĩa khác nhau đối với trạng thái cuối cùng của pipeline.

## 8. Phạm vi tác động trong build nhiều project

Một build Gradle có thể có nhiều project và nhiều task kiểm thử:

~~~text
Root build
  |
  +--> :app
  |      +--> test
  |      +--> integrationTest
  |
  +--> :service
  |      +--> test
  |
  +--> :shared
         +--> test
~~~

Một cấu hình trong project `app` thường chỉ áp dụng cho task của project đó. Một cấu hình đặt ở root hoặc trong `allprojects`/`subprojects` có thể ảnh hưởng nhiều project tùy cách viết.

Ví dụ cấu hình mọi Test task trong các subproject:

~~~groovy
subprojects {
    tasks.withType(Test).configureEach {
        ignoreFailures = true
    }
}
~~~

Đoạn này mở rộng phạm vi đến các subproject. Cần cân nhắc kỹ trước khi dùng, vì unit test của một thư viện dùng chung cũng có thể bị chuyển thành non-blocking.

Nếu chỉ một task có thể được bỏ qua, hãy cấu hình task đó theo project path hoặc trong build script sở hữu task. Khi chạy command line, dùng task path cụ thể và xác nhận graph bằng `--dry-run`.

### Test task và test suite không phải lúc nào cũng cùng tên

Plugin hoặc cấu hình testing suites có thể đăng ký task riêng như `integrationTest`, `functionalTest` hoặc task khác. Đừng giả định chỉ có task tên `test`.

Để tìm các task hiện có:

~~~shell
./gradlew tasks --all
~~~

Sau đó xem chi tiết task:

~~~shell
./gradlew help --task integrationTest
~~~

Task cụ thể và cách đăng ký phụ thuộc plugin cũng như build script của project.

## 9. Tác động đến báo cáo và trạng thái build

Bỏ qua test và ignore failure làm thay đổi bằng chứng mà pipeline tạo ra.

| Trường hợp | Test result/report | Trạng thái build |
|---|---|---|
| Test chạy và pass | Có kết quả test pass | Thành công nếu task khác cũng thành công |
| Test chạy và fail, mặc định | Có kết quả fail | Thất bại |
| Test chạy và fail, `ignoreFailures = true` | Có kết quả fail | Có thể thành công nếu task khác thành công |
| Test task bị `-x` loại khỏi graph | Không có kết quả mới từ task đó trong lần chạy | Có thể thành công |
| Test task bị `enabled = false` hoặc `onlyIf` skip | Task được đánh dấu skip; không có lượt thực thi test mới | Có thể thành công |
| Chỉ chạy một phần bằng filter | Có kết quả cho tập test được chọn | Thành công/thất bại theo kết quả và cấu hình |

Không nên dùng trạng thái build duy nhất để kết luận chất lượng kiểm thử. Một pipeline có thể xanh vì task test đã bị loại, bị disable hoặc được cấu hình ignore failure.

### Report cũ có thể gây hiểu nhầm

Nếu task test không chạy, report từ lần build trước có thể vẫn còn trong thư mục output. Việc nhìn thấy một file report không chứng minh report đó thuộc lần build hiện tại.

Khi cần đối chiếu, kiểm tra thời điểm tạo report, log của lần build và task outcome. CI nên lưu report gắn với đúng build/job/commit để tránh nhầm kết quả cũ với kết quả mới.

Với Gradle Java plugin, report HTML thường nằm dưới thư mục dạng `build/reports/tests/test/`, nhưng đường dẫn có thể thay đổi theo task hoặc cấu hình. Kết quả XML thường được đặt trong `build/test-results/`. Hãy xem cấu hình thực tế của task.

## 10. Tác động đến chất lượng và độ tin cậy của CI

Test là một phần của bằng chứng cho thấy thay đổi không làm hỏng hành vi đã có. Bỏ qua test làm giảm bằng chứng đó; ignore failure giữ lại bằng chứng nhưng thay đổi cách pipeline diễn giải nó.

### Khi bỏ qua test

Những rủi ro thường gặp:

- Lỗi regression có thể đi qua build mà không được phát hiện.
- Test compilation có thể không chạy nếu task chỉ phục vụ test bị loại khỏi graph.
- Báo cáo test mới có thể không được tạo.
- Pipeline xanh có thể bị hiểu nhầm là thay đổi đã vượt qua quality gate.
- Artifact có thể được đóng gói hoặc publish dù chưa có kết quả kiểm thử tương ứng.

### Khi ignore test failures

Rủi ro khác:

- Báo cáo vẫn cho thấy test thất bại, nhưng trạng thái build có thể xanh.
- Người xem dashboard có thể chỉ nhìn kết quả job và bỏ qua report.
- Test flaky hoặc regression thật có thể tồn tại lâu vì không chặn merge/release.
- Nhiều task test có thể cùng bị ảnh hưởng nếu cấu hình quá rộng.

`ignoreFailures` có thể hữu ích trong một giai đoạn chuyển tiếp có chủ đích, ví dụ cần thu thập report của integration test không ổn định trong khi một nhóm khác chịu trách nhiệm xử lý. Nhưng kết quả non-blocking cần được thể hiện rõ ở pipeline và có người sở hữu việc xử lý.

### Tách quality gate theo mục tiêu

Một pipeline có thể phân chia các bước:

~~~text
Compile
  |
  v
Unit tests (blocking)
  |
  v
Integration tests (non-blocking temporarily)
  |
  v
Package
  |
  v
Publish / deploy gate
~~~

Nếu integration test tạm thời không blocking, pipeline vẫn nên lưu report, hiển thị số test fail và có cơ chế theo dõi. Không nên để một job xanh duy nhất che khuất việc một nhóm test chưa đạt.

## 11. Dùng skip có kiểm soát theo môi trường

Một số nhóm test có thể cần dịch vụ bên ngoài, dữ liệu lớn hoặc môi trường đặc biệt. Có thể cấu hình để chỉ chạy chúng khi pipeline cung cấp điều kiện cần thiết.

Ví dụ dùng project property:

~~~groovy
def runIntegrationTests = providers.gradleProperty('runIntegrationTests')
    .map { it.toBoolean() }
    .getOrElse(false)

tasks.named('integrationTest', Test) {
    onlyIf {
        runIntegrationTests
    }
}
~~~

Mặc định integration test không chạy. Khi môi trường đã sẵn sàng, gọi:

~~~shell
./gradlew integrationTest -PrunIntegrationTests=true
~~~

Cách này cần được dùng có chủ đích. Nếu integration test là quality gate bắt buộc của CI, pipeline phải truyền property và có thể kiểm tra rõ rằng task không bị skip ngoài ý muốn.

### Phân biệt local convenience với CI policy

| Môi trường | Cách dùng hợp lý |
|---|---|
| Local khi sửa một class | Dùng `--tests` để chạy test liên quan |
| Local khi chỉ kiểm tra packaging | Có thể dùng `-x test` tạm thời và ghi rõ trong lệnh |
| CI pull request | Chạy các test bắt buộc; tránh skip hoặc ignore failure âm thầm |
| CI nightly | Có thể chạy bộ test rộng hơn và lưu report đầy đủ |
| Release pipeline | Xác định rõ quality gate bắt buộc; không để test bắt buộc bị loại hoặc non-blocking ngoài chính sách |
| Debug test flaky | Có thể chạy lại hoặc tạm thu thập report non-blocking theo quyết định có thời hạn |

Nếu cần một ngoại lệ, nên gắn nó với một pipeline/job cụ thể thay vì thay đổi cấu hình mặc định cho toàn repository.

## 12. Cách nhận biết test bị skip hay test fail bị bỏ qua

Khi đọc log, cần xác định task outcome và kết quả test riêng.

Một số dấu hiệu:

- `SKIPPED`: task không thực thi action theo điều kiện hoặc trạng thái cấu hình.
- `UP-TO-DATE`: Gradle xác định output còn hợp lệ; không có nghĩa test bị bỏ qua bằng cờ skip.
- `FROM-CACHE`: output được khôi phục từ build cache; task không thực hiện action trong lần chạy này.
- Test report có test failure nhưng build thành công: có thể task đang dùng `ignoreFailures`.
- Không có task test trong graph: có thể task bị loại bằng `-x`, hoặc lệnh được gọi không yêu cầu task đó.

Các trạng thái này có ý nghĩa khác nhau. Đặc biệt, `UP-TO-DATE` và `FROM-CACHE` là hành vi tối ưu hóa hợp lệ của Gradle; chúng không tương đương với việc người dùng chủ động tắt kiểm thử.

### Xác nhận task graph

~~~shell
./gradlew build --dry-run
~~~

Để kiểm tra một lệnh có loại task test không:

~~~shell
./gradlew build -x test --dry-run
~~~

### Xem log task

~~~shell
./gradlew test --info
~~~

Log giúp xác định task có được thực thi, bị skip hoặc dùng output có sẵn. Nếu task được cấu hình ignore failure, hãy đọc thêm phần summary và report test để biết kết quả thực tế.

## 13. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| `-x test` và `ignoreFailures = true` giống nhau | Một cách loại task khỏi graph; cách còn lại vẫn chạy test nhưng không để test failure làm task thất bại theo mặc định |
| `enabled = false` giống `-x` | Task disabled có thể vẫn xuất hiện trong graph và dependencies vẫn có thể chạy |
| `onlyIf` false loại toàn bộ dependency | `onlyIf` quyết định action của task; dependency vẫn có thể được thực thi |
| `--continue` làm build xanh dù có task fail | Nó tiếp tục task độc lập nhưng build vẫn thất bại nếu có task thất bại |
| Build xanh nghĩa mọi test đều pass | Test có thể không chạy hoặc failure có thể được ignore |
| Có report HTML nghĩa test vừa chạy | Report có thể là output cũ từ lần build trước |
| `tasks.withType(Test)` chỉ cấu hình task `test` | Nó có thể áp dụng cho cả `integrationTest` và các Test task khác |
| Test filter là bỏ task test | Filter giữ task chạy nhưng chỉ chọn một tập test |
| Bỏ qua test luôn bỏ qua test compilation | Tùy cách bỏ task và các dependency khác trong graph |
| `ignoreFailures` che được lỗi compile test | Nó chủ yếu thay đổi xử lý test failure; lỗi compile/resolve/worker vẫn có thể làm build thất bại |

## 14. Quy trình chọn cách xử lý phù hợp

Khi cần thay đổi hành vi kiểm thử, hãy đi theo trình tự:

1. **Xác định mục tiêu**: không muốn chạy test, muốn chạy ít test hơn, hay muốn test chạy nhưng không chặn build?
2. **Xác định task**: `test`, `integrationTest` hay task kiểm thử do plugin tạo?
3. **Xác định phạm vi**: một lần gọi, một task, mọi Test task của project hay nhiều subproject?
4. **Chọn cơ chế**:
   - Một lần bỏ task khỏi graph: `-x`.
   - Tắt task theo cấu hình: `enabled = false`.
   - Skip theo điều kiện: `onlyIf`.
   - Chạy một tập test: `--tests` hoặc test filter.
   - Vẫn chạy và không fail build vì test failure: `ignoreFailures`.
   - Tiếp tục task độc lập nhưng giữ build failed: `--continue`.
5. **Xem graph**: dùng `--dry-run` để biết task và dependency nào còn chạy.
6. **Xem kết quả**: kiểm tra task outcome, test report và trạng thái build.
7. **Giới hạn ngoại lệ**: bảo đảm CI/release không vô tình dùng cấu hình skip hoặc ignore ngoài ý muốn.

Ví dụ lựa chọn:

| Tình huống | Hướng xử lý |
|---|---|
| Đang sửa `OrderService` và chỉ cần test class đó | `./gradlew test --tests "com.example.OrderServiceTest"` |
| Muốn kiểm tra packaging một lần trên local | `./gradlew build -x test` |
| Integration test chỉ chạy khi có database test | Dùng `onlyIf`/property và cấu hình CI cung cấp điều kiện |
| Muốn thu thập report integration test dù có failure | Cấu hình `ignoreFailures` riêng cho `integrationTest`, đồng thời lưu report |
| Muốn chạy các task độc lập để thu thập nhiều lỗi | `--continue`; đọc trạng thái build vẫn có thể failed |
| Release yêu cầu mọi test bắt buộc phải pass | Giữ hành vi mặc định, không skip và không ignore failure |

Bỏ qua task và bỏ qua lỗi là những công cụ điều khiển build, không phải bằng chứng chất lượng. Khi chọn đúng cơ chế và giới hạn rõ phạm vi, có thể tiết kiệm thời gian hoặc thu thập thêm thông tin mà vẫn giữ được ý nghĩa của log, report và trạng thái pipeline.
