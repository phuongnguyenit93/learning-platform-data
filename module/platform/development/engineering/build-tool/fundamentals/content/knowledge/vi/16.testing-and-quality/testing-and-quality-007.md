# Báo cáo độ bao phủ và giới hạn của một con số phần trăm

Độ bao phủ kiểm thử (test coverage) cho biết một phần mã nguồn đã được thực thi trong những lần chạy kiểm thử được đo hay chưa. Báo cáo coverage giúp nhóm tìm vùng mã chưa được kiểm tra, nhận diện nhánh điều kiện chưa đi qua và theo dõi thay đổi theo thời gian. Tuy nhiên, một con số như “85% coverage” không chứng minh ứng dụng đúng, test có assertion tốt hay mọi tình huống quan trọng đã được kiểm tra.

Muốn sử dụng coverage đúng cách, cần biết công cụ đang đo loại coverage nào, mẫu số gồm những class/file nào, test nào đã chạy, dữ liệu thực thi được thu thập ra sao và ngưỡng phần trăm được áp dụng ở đâu. Với dự án Java dùng Gradle, JaCoCo là công cụ phổ biến để thu thập dữ liệu thực thi, tạo báo cáo HTML/XML và kiểm tra ngưỡng coverage trong build.

## 1. Độ bao phủ kiểm thử đo điều gì?

Coverage là phép đo mức độ mã được thực thi trong một lần hoặc một nhóm lần chạy. Công cụ coverage gắn bộ theo dõi vào bytecode hoặc dùng cơ chế instrumentation để ghi nhận những phần mã đã được thực thi. Sau khi test kết thúc, công cụ đối chiếu dữ liệu thực thi với các class được đưa vào báo cáo.

Ví dụ, một phương thức có hai nhánh:

```java
public String classify(int age) {
    if (age >= 18) {
        return "adult";
    }
    return "minor";
}
```

Nếu test chỉ gọi `classify(20)`, dòng kiểm tra điều kiện và nhánh `adult` được thực thi, nhưng nhánh `minor` chưa được đi qua. Báo cáo có thể cho biết dòng hoặc nhánh chưa được bao phủ. Điều đó gợi ý cần xem test cho trường hợp tuổi dưới 18, nhưng không tự chứng minh test hiện tại kiểm tra kết quả đúng.

Coverage thường được biểu diễn bằng tỷ lệ:

\[
\text{Coverage} = \frac{\text{Số phần tử đã được bao phủ}}{\text{Tổng số phần tử được tính}} \times 100\%
\]

“Phần tử” trong công thức phụ thuộc loại coverage: instruction, line, branch, method hoặc class. Do đó, trước khi so sánh hai tỷ lệ, cần xác nhận chúng đang dùng cùng một loại phép đo và cùng phạm vi mã.

## 2. Các loại coverage thường gặp

Một báo cáo JaCoCo có thể hiển thị nhiều counter. Mỗi counter trả lời một câu hỏi khác nhau.

| Loại coverage | Đo lường | Điều nó giúp phát hiện |
|---|---|---|
| Instruction coverage | Số bytecode instruction đã thực thi. | Mức độ thực thi ở mức bytecode; chi tiết hơn line coverage. |
| Line coverage | Số dòng mã nguồn có ít nhất một instruction được thực thi. | Dòng nào chưa được chạy trong test. |
| Branch coverage | Số nhánh điều khiển đã đi qua, thường gồm nhánh `if` và `switch`. | Điều kiện hoặc hướng rẽ nào chưa được kiểm tra. |
| Method coverage | Số method đã được thực thi ít nhất một lần. | Method nào chưa được gọi trong phạm vi đo. |
| Class coverage | Số class đã được thực thi ít nhất một lần. | Class nào chưa được chạm tới. |
| Complexity coverage | Mức độ bao phủ các nhánh độc lập liên quan đến cyclomatic complexity. | Gợi ý phần logic rẽ nhánh còn chưa được thực thi. |

Không nên gộp các counter thành một ý nghĩa chung. Một project có thể có 95% line coverage nhưng branch coverage thấp hơn nhiều nếu các test chỉ đi qua một hướng trong những điều kiện phức tạp.

### 2.1. Instruction coverage

Java compiler chuyển mã nguồn thành bytecode. Một dòng Java có thể tạo ra nhiều instruction, và nhiều dòng có thể được ánh xạ thành một nhóm instruction. JaCoCo theo dõi instruction ở mức bytecode để đo phần instruction đã thực thi.

Instruction coverage có thể phát hiện một phần mã chưa chạy ngay cả khi line coverage có vẻ cao. Tuy nhiên, instruction là đơn vị kỹ thuật của bytecode, không phải đơn vị hành vi nghiệp vụ. Một tỷ lệ instruction cao không nói test đã kiểm tra kết quả, ngoại lệ hoặc trạng thái sau thao tác.

### 2.2. Line coverage

Line coverage cho biết dòng mã nguồn có instruction được thực thi hay không. Dòng được tính là covered nếu ít nhất một instruction tương ứng đã chạy; nếu không instruction nào chạy, dòng đó là missed.

Ví dụ:

```java
public int discount(int amount) {
    if (amount > 1000) {
        return 100;
    }
    return 0;
}
```

Một test với `amount = 1500` có thể thực thi dòng `return 100`, nhưng chưa thực thi `return 0`. Line report làm lộ dòng chưa được chạy. Tuy nhiên, line coverage không thể hiện test có xác nhận giá trị trả về hay không.

Line coverage phụ thuộc thông tin debug/source mapping được compiler ghi vào class file. Nếu thiếu thông tin dòng nguồn hoặc mã được sinh tự động, báo cáo có thể hiển thị khác với kỳ vọng.

### 2.3. Branch coverage

Branch coverage tập trung vào các nhánh điều khiển. Với `if/else`, mỗi hướng có thể là một branch riêng. Với `switch`, các lựa chọn tạo ra các nhánh tương ứng. Một test suite có thể thực thi dòng điều kiện nhưng chỉ đi qua một hướng, nên line coverage cao trong khi branch coverage thấp.

Ví dụ:

```java
public boolean canWithdraw(int balance, int amount) {
    if (amount > 0 && amount <= balance) {
        return true;
    }
    return false;
}
```

Các tình huống cần xem xét gồm:

- `amount` dương và không vượt số dư.
- `amount` bằng 0 hoặc âm.
- `amount` lớn hơn số dư.
- `balance` ở giá trị biên.

Branch coverage giúp phát hiện hướng rẽ chưa được thực thi, nhưng không đồng nghĩa đã kiểm tra mọi tổ hợp của các toán hạng boolean. Nó cũng không phải phép đo MC/DC hay exhaustive condition coverage. Một điều kiện phức hợp có nhiều tổ hợp đầu vào hơn số branch mà công cụ báo cáo.

### 2.4. Method và class coverage

Method coverage tính method đã được gọi ít nhất một lần; class coverage tính class đã được thực thi ít nhất một lần. Hai tỷ lệ này có ích để tìm code hoàn toàn chưa được chạm tới, nhưng ít chi tiết hơn line/branch coverage.

Một method có thể được gọi nhưng chỉ thực hiện một phần nhánh. Một class có thể được khởi tạo nhưng các method quan trọng chưa được gọi. Vì vậy, method/class coverage thường nên được đọc cùng line và branch coverage.

### 2.5. Complexity coverage

JaCoCo tính cyclomatic complexity từ cấu trúc điều khiển của bytecode. Chỉ số này phản ánh số đường đi độc lập tối thiểu cần xem xét để bao phủ các nhánh theo mô hình tương ứng. Complexity coverage cho biết phần complexity đã được bao phủ so với tổng complexity được tính.

Complexity không phải số test cần viết chính xác và cũng không đo độ khó nghiệp vụ. Một method có complexity thấp vẫn có thể cần nhiều test vì dữ liệu biên, trạng thái, lỗi phụ thuộc hoặc tương tác bên ngoài.

## 3. Vì sao một tỷ lệ phần trăm có thể gây hiểu nhầm?

Tỷ lệ coverage luôn có mẫu số. Nếu phạm vi được tính thay đổi, phần trăm có thể thay đổi dù chất lượng test không đổi.

Giả sử project có 100 dòng được tính và 80 dòng đã được thực thi. Line coverage là 80%. Nếu nhóm loại 20 dòng khỏi phạm vi báo cáo mà không thay đổi test, tỷ lệ có thể tăng lên 100% trên 80 dòng còn lại. Mã chưa được kiểm tra vẫn tồn tại; mẫu số đã thay đổi.

Một số yếu tố làm tỷ lệ thay đổi:

- Thêm hoặc xóa class khỏi phạm vi báo cáo.
- Loại generated code, DTO, cấu hình hoặc adapter khỏi báo cáo.
- Thay đổi source set hoặc test suite được đưa vào lần chạy.
- Chạy thêm integration test hoặc loại test khỏi CI.
- Dùng class file khác với source revision đang được xem.
- Dữ liệu execution cũ còn sót lại hoặc nhiều lần chạy được gộp với nhau.
- Thay đổi cách công cụ ánh xạ bytecode về source line.

Do đó, con số phần trăm chỉ có ý nghĩa khi đi kèm phạm vi mã, loại counter, tập test và commit/build tạo ra dữ liệu.

## 4. Coverage cao không đồng nghĩa test tốt

Coverage đo mã có được thực thi, không đo chất lượng assertion. Một test có thể gọi mọi method nhưng không xác nhận kết quả.

Ví dụ test sau có thể làm method được tính là covered:

```java
@Test
void calculatesTotal() {
    PriceCalculator calculator = new PriceCalculator();
    calculator.total(200, 3);
}
```

Test không có assertion nên vẫn có thể pass nếu phương thức trả về kết quả sai. Test tốt cần xác nhận hành vi:

```java
@Test
void calculatesTotal() {
    PriceCalculator calculator = new PriceCalculator();

    assertEquals(600, calculator.total(200, 3));
}
```

Ngay cả khi có assertion, test có thể chỉ xác nhận một trường hợp bình thường mà bỏ qua dữ liệu biên, lỗi đầu vào, trạng thái bất thường hoặc side effect. Coverage không đánh giá tính độc lập của test, độ rõ của assertion, độ ổn định, khả năng tái lập hay mức độ đại diện của dữ liệu.

Một số cách làm tăng coverage mà không cải thiện đáng kể chất lượng:

- Gọi method chỉ để dòng lệnh được đánh dấu covered nhưng không assert kết quả.
- Viết test cho getter/setter đơn giản trong khi logic nghiệp vụ quan trọng chưa được kiểm tra.
- Loại nhiều package khỏi báo cáo để tăng tỷ lệ.
- Tạo test quá phụ thuộc implementation khiến thay đổi nội bộ nhỏ cũng làm test hỏng.
- Chỉ chạy test dễ pass và bỏ qua test tích hợp quan trọng.

Coverage nên được dùng để tìm câu hỏi cần đặt ra: “Vì sao đoạn mã này chưa được chạy?” và “Nếu chạy nhánh này, test sẽ xác nhận điều gì?”. Không nên dùng nó như mục tiêu tối đa hóa độc lập với hành vi sản phẩm.

## 5. Thu thập coverage bằng JaCoCo trong Gradle

JaCoCo là công cụ đo coverage cho Java. Gradle cung cấp plugin `jacoco` để gắn agent thu thập dữ liệu vào test task, lưu execution data và tạo report.

Ví dụ `build.gradle` dùng Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'jacoco'
}

jacoco {
    toolVersion = '0.8.13'
}

tasks.test {
    useJUnitPlatform()
    finalizedBy tasks.jacocoTestReport
}

tasks.jacocoTestReport {
    dependsOn tasks.test

    reports {
        html.required = true
        xml.required = true
        csv.required = false
    }
}
```

Version JaCoCo trong ví dụ là một giá trị minh họa đã pin rõ ràng; dự án nên chọn bản phù hợp với JDK, Gradle và chính sách nâng cấp của mình. Không nên để version công cụ coverage thay đổi ngầm giữa các lần build.

Plugin tạo task `jacocoTestReport` để phân tích execution data của task test và tạo báo cáo. Với cấu hình mặc định, HTML report thường nằm dưới `build/reports/jacoco/test/html/`, còn XML report nằm dưới `build/reports/jacoco/test/jacocoTestReport.xml`. Đường dẫn có thể thay đổi nếu project tùy chỉnh report destination.

### 5.1. Ý nghĩa `finalizedBy` và `dependsOn`

Trong ví dụ:

- `test.finalizedBy jacocoTestReport` đăng ký report task làm finalizer của test, để báo cáo được chạy sau test khi task test được thực thi.
- `jacocoTestReport.dependsOn test` bảo đảm report task có dữ liệu test mới bằng cách yêu cầu test chạy trước.

Khai báo cả hai thường được dùng để người phát triển có thể gọi `test` và nhận report. Nếu chỉ gọi `jacocoTestReport`, dependency bảo đảm test chạy trước. Với các build có nhiều test task hoặc suite riêng, cần cấu hình report tương ứng cho từng execution data source.

### 5.2. Kotlin DSL

Ví dụ `build.gradle.kts`:

```kotlin
plugins {
    java
    jacoco
}

jacoco {
    toolVersion = "0.8.13"
}

tasks.test {
    useJUnitPlatform()
    finalizedBy(tasks.jacocoTestReport)
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        html.required.set(true)
        xml.required.set(true)
        csv.required.set(false)
    }
}
```

Tên task và API report được plugin JaCoCo cung cấp. Khi dùng Gradle version khác hoặc custom test suite, hãy kiểm tra API tương ứng của phiên bản Gradle trong dự án.

## 6. Đọc báo cáo JaCoCo

Báo cáo HTML thường có cấu trúc phân cấp:

```text
build/reports/jacoco/test/html/
├── index.html
└── com.example/
    ├── index.html
    └── PriceCalculator.html
```

Trang tổng quan cho biết tỷ lệ theo package và project. Có thể đi vào package, class và source view để xem dòng được bao phủ hoặc bị bỏ sót. JaCoCo thường tô màu để phân biệt dòng covered, partly covered và missed; màu sắc cụ thể phụ thuộc giao diện report.

Khi mở report, hãy đọc theo thứ tự:

1. Xác nhận report thuộc đúng build/commit và test run.
2. Xem counter đang được quan tâm, chẳng hạn line hay branch.
3. Xác định package/class đóng góp nhiều missed instructions hoặc branches.
4. Mở source view để tìm nhánh chưa chạy.
5. Đọc logic nghiệp vụ và xác định test nào cần bổ sung.
6. Viết test có assertion về kết quả hoặc trạng thái quan trọng.

Không nên chỉ chọn class có tỷ lệ thấp nhất. Một class tiện ích ít rủi ro có thể có coverage thấp hơn service xử lý thanh toán hoặc phân quyền. Ưu tiên dựa trên mức độ ảnh hưởng, độ phức tạp, khả năng gây thiệt hại và tần suất thay đổi.

## 7. Đặt ngưỡng coverage và làm build thất bại khi không đạt

Coverage report cho biết kết quả; coverage verification áp dụng quy tắc để build có thể dừng nếu tỷ lệ dưới ngưỡng. Với Gradle JaCoCo, task `jacocoTestCoverageVerification` thực hiện việc kiểm tra này.

Ví dụ đặt ngưỡng line coverage tối thiểu 80%:

```groovy
tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}
```

`minimum = 0.80` có nghĩa tỷ lệ line covered phải đạt ít nhất 0.80, tức 80%. Đây là tỷ lệ dạng số thập phân, không phải số 80.

Task verification không tự động trở thành một phần của `check` trong cấu hình mặc định. Nếu muốn CI chạy kiểm tra coverage mỗi khi gọi `check`, hãy nối task rõ ràng:

```groovy
tasks.check {
    dependsOn tasks.jacocoTestCoverageVerification
}
```

Khi đó:

```bash
./gradlew check
```

sẽ chạy test và kiểm tra coverage theo dependency graph được cấu hình. Nếu ngưỡng không đạt, verification task thất bại và `check`/`build` cũng thất bại.

### 7.1. Kiểm tra nhiều loại counter

Có thể đặt các ngưỡng riêng cho line và branch:

```groovy
tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
            limit {
                counter = 'BRANCH'
                value = 'COVEREDRATIO'
                minimum = 0.70
            }
        }
    }
}
```

Các limit trong cùng rule đều phải thỏa mãn. Có thể đặt thêm rule riêng theo class hoặc package để kiểm soát phần code quan trọng.

### 7.2. Giới hạn theo class/package

Ví dụ chỉ áp dụng rule cho class thuộc package nghiệp vụ:

```groovy
tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            element = 'CLASS'
            includes = ['com.example.service.*']

            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.85
            }
        }
    }
}
```

Rule này giới hạn class được xét theo pattern include. Cần xác nhận pattern khớp tên class mà JaCoCo báo cáo, đặc biệt với inner class và generated class. Nếu không class nào khớp, rule có thể không tạo ra kiểm tra như nhóm dự định.

## 8. Chọn ngưỡng có ý nghĩa

Không có một tỷ lệ coverage phù hợp cho mọi dự án. Ngưỡng phụ thuộc vào loại sản phẩm, mức rủi ro, độ trưởng thành của test suite, khả năng kiểm soát hệ thống ngoài và chi phí bảo trì.

Một chính sách thực tế có thể:

- Đặt ngưỡng tối thiểu ở mức project để ngăn coverage giảm liên tục.
- Đặt ngưỡng cao hơn cho package nghiệp vụ quan trọng như thanh toán, phân quyền hoặc tính giá.
- Ưu tiên branch coverage cho logic có nhiều điều kiện và nhiều trường hợp biên.
- Cho phép ngoại lệ có lý do với generated code, adapter hoặc mã phụ thuộc nền tảng.
- Tăng ngưỡng dần khi nhóm cải thiện test suite, thay vì đặt mục tiêu cao đột ngột khiến mọi thay đổi bị chặn.
- Xem xét coverage mới được thêm trong pull request bên cạnh tỷ lệ tổng thể của repository.

Một ngưỡng 100% line coverage có thể không thực tế hoặc không đáng chi phí với mọi hệ thống. Ngược lại, một ngưỡng thấp cũng không bảo đảm phần code rủi ro được kiểm tra. Tỷ lệ nên là tín hiệu kiểm soát, còn quyết định ưu tiên cần dựa trên rủi ro nghiệp vụ và cấu trúc code.

## 9. Loại trừ code khỏi báo cáo một cách có trách nhiệm

Một số class được sinh tự động hoặc không thuộc phạm vi test trực tiếp có thể làm tỷ lệ tổng thể khó diễn giải. JaCoCo cho phép giới hạn class directories được phân tích.

Ví dụ loại generated class khỏi report:

```groovy
tasks.jacocoTestReport {
    classDirectories.setFrom(files(classDirectories.files.collect {
        fileTree(dir: it, exclude: [
            '**/generated/**',
            '**/*Generated.class'
        ])
    }))
}
```

Nếu loại class khỏi report nhưng không loại tương ứng khỏi verification, report và ngưỡng có thể đánh giá hai phạm vi khác nhau. Khi tùy chỉnh class directories, cần áp dụng cùng phạm vi cho `jacocoTestReport` và `jacocoTestCoverageVerification`.

Không nên loại code chỉ vì khó viết test hoặc tỷ lệ thấp. Mã generated, framework glue hoặc class được sinh bởi annotation processor có thể cần cách kiểm tra khác, nhưng logic nghiệp vụ được viết thủ công vẫn nên nằm trong phạm vi đo. Mỗi exclusion nên có lý do, owner và thời điểm xem xét lại.

## 10. Phân biệt unit test, integration test và dữ liệu coverage

Coverage phản ánh những test đã chạy với agent JaCoCo được gắn vào tiến trình. Nếu CI chỉ chạy unit test, report chỉ thể hiện phần code mà unit test thực thi. Integration test có thể đi qua những đường code khác, nhưng chỉ được tính nếu execution data của chúng được đưa vào report.

Một dự án có thể tách task:

```groovy
tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    shouldRunAfter tasks.test
}
```

Đây chỉ là khung minh họa cho task test riêng; project thực tế thường cần source set `integrationTest` riêng, dependency configuration và test filtering phù hợp. JaCoCo plugin có thể tạo execution data riêng cho mỗi `Test` task. Để gộp kết quả, report phải đọc các execution data file tương ứng.

Ví dụ cấu hình report nhận nhiều execution data:

```groovy
tasks.register('combinedCoverageReport', JacocoReport) {
    dependsOn tasks.test, tasks.integrationTest

    executionData tasks.test, tasks.integrationTest
    sourceDirectories.from(sourceSets.main.allSource.srcDirs)
    classDirectories.from(sourceSets.main.output)

    reports {
        html.required = true
        xml.required = true
    }
}
```

Tên task và source set cần khớp cấu hình thật của project. Gộp execution data giúp thấy coverage từ cả hai loại test, nhưng report cần được tạo từ cùng phiên bản class/source. Nếu test chạy trên các binary khác nhau hoặc execution data cũ bị trộn vào, kết quả có thể không phản ánh chính xác revision hiện tại.

Với multi-project build, Gradle có plugin `jacoco-report-aggregation` để tổng hợp coverage từ các project/test suite được khai báo. Nên dùng cơ chế aggregation phù hợp thay vì tự ghép file `.exec` bằng script không kiểm soát.

## 11. Coverage trong CI và báo cáo XML

HTML report thuận tiện cho lập trình viên đọc chi tiết. XML report thường được CI, code quality platform hoặc công cụ phân tích pull request dùng để nhập kết quả.

Trong pipeline, một quy trình thường gồm:

1. Checkout đúng commit.
2. Chạy test suite cần đo.
3. Tạo JaCoCo report.
4. Chạy coverage verification theo ngưỡng.
5. Lưu HTML report làm artifact để điều tra.
6. Publish XML report cho công cụ CI/quality nếu có.

Nếu CI chỉ lưu log mà không giữ report, lập trình viên sẽ khó tìm class/branch chưa được bao phủ. Nếu pipeline chỉ upload XML nhưng không xác minh report thuộc đúng commit, dashboard có thể hiển thị dữ liệu cũ hoặc sai revision.

Nên giữ tên và đường dẫn report ổn định để pipeline dễ thu thập. Khi chạy nhiều test task, cần quy ước report tổng hợp và report riêng để người đọc hiểu coverage đến từ unit test hay integration test.

## 12. Những giới hạn quan trọng của coverage

Coverage là một phép đo thực thi có phạm vi hữu hạn. Nó không thay thế các phương pháp kiểm thử khác.

**Không đo tính đúng đắn của assertion.** Dòng được chạy nhưng test không kiểm tra kết quả thì coverage vẫn có thể tăng.

**Không đo chất lượng dữ liệu test.** Một nhánh có thể được chạy với dữ liệu quá đơn giản, không phản ánh biên hoặc trạng thái lỗi.

**Không chứng minh mọi đường đi đã được kiểm tra.** Branch coverage chỉ xét các nhánh theo mô hình công cụ; tổ hợp điều kiện và path phức tạp có thể còn nhiều trường hợp chưa thử.

**Không đo concurrency đầy đủ.** Test có thể chạy một luồng và tạo coverage cao, nhưng không phát hiện race condition, deadlock hoặc vấn đề thứ tự giữa các thread.

**Không chứng minh tích hợp với hệ thống ngoài.** Mock có thể làm code adapter được thực thi mà không kiểm tra giao thức, cấu hình hoặc hành vi thật của database, broker hay dịch vụ mạng.

**Không đo độ ổn định của test.** Test flaky có thể tạo report khác nhau giữa các lần chạy; tỷ lệ trung bình không cho biết test có tái lập hay không.

**Không đo security coverage.** Một đoạn code xác thực được chạy không chứng minh mọi đường tấn công, quyền truy cập hoặc dữ liệu độc hại đã được kiểm tra.

**Không đánh giá code chưa được đưa vào phạm vi.** Class bị exclude, source set không được report hoặc module không được đưa vào aggregation không xuất hiện trong mẫu số.

**Không thể so sánh trực tiếp giữa công cụ/cấu hình khác nhau.** Khác counter, filter, compiler, test suite và source mapping có thể tạo ra tỷ lệ không cùng ý nghĩa.

## 13. Kết hợp coverage với các kỹ thuật kiểm thử khác

Để đánh giá chất lượng tốt hơn, có thể kết hợp coverage với:

- **Assertion review:** xác nhận mỗi test kiểm tra kết quả, trạng thái hoặc side effect quan trọng.
- **Boundary testing:** thử giá trị biên, giá trị rỗng, cực đại/cực tiểu và dữ liệu không hợp lệ.
- **Mutation testing:** cố ý thay đổi logic nhỏ để xem test có phát hiện được lỗi hay không. Mutation score bổ sung thông tin về khả năng phát hiện lỗi của test.
- **Property-based testing:** sinh nhiều dữ liệu đầu vào theo thuộc tính cần giữ đúng, thay vì chỉ dựa vào vài ví dụ cố định.
- **Integration/contract testing:** kiểm tra giao tiếp giữa module và hệ thống ngoài theo hợp đồng.
- **Static analysis:** phát hiện một số lỗi và pattern nguy hiểm mà test runtime có thể chưa chạm tới.
- **Code review theo rủi ro:** tập trung vào logic có ảnh hưởng lớn, thay đổi mới và các đường xử lý lỗi.

Coverage giúp tìm vùng chưa được thực thi; các kỹ thuật khác giúp đánh giá liệu test có phát hiện được hành vi sai hay không. Một test suite tốt thường kết hợp nhiều cách tiếp cận thay vì cố đạt một tỷ lệ duy nhất.

## 14. Điều tra khi report thiếu hoặc tỷ lệ bất thường

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không có HTML report | Report task chưa chạy, test thất bại trước khi tạo dữ liệu hoặc HTML report bị tắt. | Chạy `jacocoTestReport`, kiểm tra `reports.html.required` và task outcome. |
| Report có nhưng không có class | Sai classDirectories/source set hoặc report không có execution data phù hợp. | Kiểm tra class output, source set và file `.exec`. |
| Coverage bằng 0% | Agent không được gắn vào tiến trình test, không có test thực thi code đó hoặc report đọc sai execution data. | Xem test task, JaCoCo agent, execution data và class directories. |
| Tỷ lệ tăng đột ngột | Phạm vi class bị loại, test suite mới được chạy hoặc dữ liệu cũ được gộp. | So sánh report configuration, execution data và commit. |
| CI khác local | JDK, test filter, test suite, task graph hoặc môi trường khác nhau. | So sánh lệnh, JDK, configuration và report artifact. |
| Verification không chạy khi gọi `check` | Task chưa được nối vào lifecycle task. | Kiểm tra `check.dependsOn jacocoTestCoverageVerification`. |
| Verification thất bại nhưng report vẫn có | Report và verification là hai task riêng; report có thể tạo được trước khi threshold fail. | Đọc task outcome và counter vi phạm. |
| Branch coverage thấp hơn line nhiều | Test chạm dòng điều kiện nhưng chưa đi qua đủ hướng rẽ. | Xem branch missed trong source view và bổ sung test cho logic quan trọng. |

Một số lệnh hữu ích:

```bash
./gradlew test jacocoTestReport --info
./gradlew jacocoTestCoverageVerification --info
./gradlew check --stacktrace
```

Sau khi thay đổi test hoặc cấu hình coverage, hãy xác nhận report đang đọc execution data mới. Khi cần loại bỏ dữ liệu build cũ để tái hiện, có thể chạy `clean` rồi chạy lại đúng test/report task; chỉ làm sau khi đã lưu report cũ nếu cần so sánh.

## 15. Ví dụ quy trình từ test đến quyết định

Giả sử JaCoCo report cho một package nghiệp vụ hiển thị:

| Counter | Covered | Missed | Coverage |
|---|---:|---:|---:|
| Instructions | 820 | 180 | 82% |
| Lines | 164 | 36 | 82% |
| Branches | 24 | 16 | 60% |
| Methods | 18 | 2 | 90% |

Các con số trên chỉ là ví dụ minh họa. Cách đọc hợp lý:

1. Method coverage 90% cho thấy phần lớn method đã được gọi ít nhất một lần.
2. Line coverage 82% cho thấy vẫn còn dòng chưa được thực thi.
3. Branch coverage 60% thấp hơn line đáng kể, gợi ý một số điều kiện mới chỉ được chạy theo một hướng.
4. Nhóm mở source report để xác định nhánh missed nằm ở logic nào.
5. Nhóm ưu tiên nhánh liên quan đến quyền truy cập hoặc tính toán tiền vì rủi ro nghiệp vụ cao.
6. Test mới cần assert kết quả và trường hợp lỗi, không chỉ gọi method.
7. Sau khi chạy lại, nhóm xem cả report và kết quả test để xác nhận thay đổi có ý nghĩa.

Nếu tỷ lệ tăng từ 82% lên 88%, đó là tín hiệu tích cực về mức độ thực thi trong phạm vi đo. Nhưng quyết định merge vẫn cần dựa vào test pass, assertion, review logic và các yêu cầu chất lượng khác.

## 16. Nguyên tắc sử dụng coverage bền vững

- Chọn rõ counter phù hợp với câu hỏi cần trả lời; line và branch thường bổ sung cho nhau.
- Công bố phạm vi mã được đo, test suite được chạy và commit tạo report.
- Giữ cấu hình JaCoCo ổn định và pin version công cụ.
- Dùng report HTML để điều tra chi tiết và XML cho CI/quality tooling.
- Đặt threshold dựa trên rủi ro, có thể tăng dần và có quy trình ngoại lệ rõ ràng.
- Nối `jacocoTestCoverageVerification` vào `check` nếu coverage là điều kiện bắt buộc của build.
- Đồng bộ exclusions giữa report và verification; không loại code chỉ để tăng phần trăm.
- Phân biệt dữ liệu unit test và integration test; chỉ gộp khi execution data và class/source cùng revision.
- Xem coverage là tín hiệu tìm vùng thiếu test, không phải bằng chứng test tốt hay ứng dụng đúng.
- Kết hợp assertion review, boundary testing, mutation testing, integration testing và code review theo rủi ro.

Báo cáo coverage có giá trị khi người đọc hiểu được counter, mẫu số, phạm vi class và tập test tạo ra dữ liệu. JaCoCo giúp Gradle thu thập execution data, hiển thị vùng mã đã chạy và áp dụng ngưỡng trong CI. Nhưng phần trăm chỉ phản ánh mức độ thực thi theo một phép đo cụ thể. Chất lượng kiểm thử còn phụ thuộc vào assertion, dữ liệu biên, tính độc lập, khả năng phát hiện lỗi và mức độ bao phủ rủi ro nghiệp vụ. Dùng coverage như công cụ định hướng điều tra và cải thiện test sẽ hữu ích hơn việc xem một con số cao là mục tiêu tự thân.
