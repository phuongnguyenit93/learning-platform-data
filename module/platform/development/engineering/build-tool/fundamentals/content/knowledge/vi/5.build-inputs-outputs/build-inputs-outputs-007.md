# Quyền sở hữu đầu ra: tránh nhiều tác vụ cùng ghi một tệp

Trong một build, nhiều tác vụ có thể cùng tham gia tạo ra một sản phẩm: một tác vụ sinh cấu hình, một tác vụ tạo mã nguồn, một tác vụ sao chép tài nguyên và một tác vụ đóng gói. Việc chia công việc thành nhiều tác vụ giúp build dễ tổ chức và có thể chạy song song. Tuy nhiên, mỗi tác vụ cần có ranh giới đầu ra rõ ràng.

Một nguyên tắc quan trọng là **mỗi tệp đầu ra được quản lý bởi một tác vụ ghi duy nhất**. Nếu hai tác vụ độc lập cùng ghi vào một đường dẫn, kết quả phụ thuộc vào thứ tự thực thi và thời điểm ghi. Khi build chạy song song, một tác vụ có thể ghi đè kết quả của tác vụ kia, hai lần ghi có thể xen kẽ, hoặc tác vụ đọc có thể nhìn thấy tệp chưa được ghi hoàn chỉnh. Những lỗi này thường khó tái hiện vì build có thể thành công ở lần chạy này và thất bại ở lần chạy khác.

Quyền sở hữu đầu ra giúp build tool hiểu tác vụ nào tạo ra dữ liệu, tác vụ nào tiêu thụ dữ liệu, khi nào cần chạy lại và phần nào có thể được lưu cache. Đây là nền tảng của build có thể dự đoán, chạy song song an toàn và tái sử dụng kết quả đáng tin cậy.

## 1. Đầu ra của một tác vụ là gì?

Một tác vụ build nhận đầu vào, thực hiện một công việc và có thể tạo ra đầu ra.

```text
Đầu vào
  |
  v
Tác vụ build
  |
  v
Đầu ra
```

Ví dụ:

| Tác vụ | Đầu vào | Đầu ra |
|---|---|---|
| Biên dịch Java | Tệp `.java`, classpath, tùy chọn compiler | Tệp `.class` |
| Xử lý tài nguyên | `src/main/resources`, bộ lọc và cấu hình | Tài nguyên đã xử lý |
| Sinh mã nguồn | Schema, template, cấu hình generator | Tệp `.java` được sinh |
| Sinh cấu hình | Tham số môi trường, template | Tệp `.properties` hoặc `.yml` |
| Đóng gói JAR | Lớp đã biên dịch và tài nguyên | Tệp `.jar` |
| Tạo báo cáo | Kết quả kiểm thử hoặc dữ liệu phân tích | HTML, XML hoặc JSON report |

Đầu ra có thể là một tệp, một nhóm tệp hoặc cả một thư mục. Ví dụ, tác vụ biên dịch Java tạo ra nhiều tệp `.class` theo cấu trúc package; tác vụ đóng gói thường tạo một tệp JAR.

Trong Gradle, một task có thể khai báo đầu ra bằng `outputs.file(...)` hoặc `outputs.dir(...)`. Với custom task có kiểu thuộc tính, các annotation như `@OutputFile` và `@OutputDirectory` biểu diễn cùng loại thông tin ở cấp property. Khai báo này cho Gradle biết những vị trí mà task chịu trách nhiệm tạo hoặc cập nhật.

## 2. Quyền sở hữu đầu ra nghĩa là gì?

Quyền sở hữu đầu ra (*output ownership*) là việc xác định rõ tác vụ nào có trách nhiệm ghi và duy trì một đầu ra cụ thể. Tác vụ sở hữu đầu ra có trách nhiệm:

- Tạo đầu ra khi tác vụ cần thực thi.
- Cập nhật đầu ra khi đầu vào hoặc cấu hình liên quan thay đổi.
- Khai báo chính xác đường dẫn đầu ra cho build tool.
- Xử lý trường hợp đầu ra cũ không còn phù hợp theo hợp đồng của tác vụ.
- Tạo kết quả xác định được từ các đầu vào đã khai báo.

Các tác vụ khác có thể đọc, sao chép hoặc sử dụng đầu ra đó. Chúng không nên tự ý ghi lại cùng tệp. Nếu cần thay đổi nội dung, hãy chuyển trách nhiệm ghi sang tác vụ sở hữu hoặc thiết kế một tác vụ mới làm chủ đầu ra cuối cùng.

Ví dụ một pipeline hợp lý:

```text
schema.json
    |
    v
generateModel
    |
    +----> build/generated/model/Product.java
    |
    v
compileJava
    |
    v
build/classes/java/main/...
    |
    v
jar
    |
    v
build/libs/application.jar
```

Trong sơ đồ này, `generateModel` sở hữu tệp Java được sinh. `compileJava` đọc tệp đó và sở hữu các lớp đã biên dịch. `jar` đọc các lớp và tài nguyên để tạo JAR. Mỗi bước có một vùng đầu ra riêng, nên có thể xác định tác vụ chịu trách nhiệm khi một sản phẩm bị sai.

## 3. Điều gì xảy ra khi nhiều tác vụ cùng ghi một tệp?

Giả sử hai tác vụ cùng ghi `build/generated/config/app.properties`:

```text
generateForDev  ----+
                   +----> app.properties
generateForProd ----+
```

Tác vụ thứ nhất muốn ghi:

```properties
environment=dev
endpoint=https://dev.example.test
```

Tác vụ thứ hai muốn ghi:

```properties
environment=prod
endpoint=https://prod.example.test
```

Hai kết quả có ý nghĩa khác nhau, nhưng chúng lại dùng chung một đường dẫn. Build không có cách tự suy ra nội dung nào là kết quả đúng.

### Ghi đè theo thứ tự thực thi

Nếu tác vụ A ghi trước và tác vụ B ghi sau, nội dung cuối cùng là của B. Nếu thứ tự thay đổi, nội dung cuối cùng có thể là của A. Khi thứ tự chạy không được xác định rõ, kết quả build cũng không ổn định.

Ngay cả khi hiện tại hai tác vụ thường chạy tuần tự, việc phụ thuộc vào thứ tự tình cờ vẫn tạo ra lỗi thiết kế. Sau này thêm dependency, bật parallel execution hoặc thay đổi cấu trúc task graph có thể làm kết quả đổi khác.

### Ghi xen kẽ hoặc đọc dữ liệu chưa hoàn chỉnh

Một tác vụ có thể mở tệp và ghi nội dung trong khi tác vụ khác cũng mở cùng tệp. Tùy cách ghi, hệ điều hành và thư viện được sử dụng, kết quả có thể bị ghi đè từng phần, bị cắt cụt hoặc chứa dữ liệu không thuộc một kết quả hoàn chỉnh nào.

Một tác vụ tiêu thụ cũng có thể đọc tệp đúng lúc tác vụ sản xuất đang cập nhật nó. Khi đó, tác vụ tiêu thụ có thể nhận dữ liệu cũ, dữ liệu mới một phần hoặc kết quả không nhất quán.

### Build cache và incremental build mất độ tin cậy

Build tool cần biết đầu ra nào thuộc về tác vụ nào để xác định tác vụ có thể được bỏ qua, chạy lại hoặc khôi phục từ cache. Nếu một tác vụ khác âm thầm sửa cùng đường dẫn, trạng thái đầu ra được ghi nhận cho mỗi task có thể không còn khớp với nội dung mà task đó dự kiến tạo ra.

Gradle kiểm tra cả đầu vào lẫn trạng thái đầu ra khi xét một task có up-to-date hay không. Vì vậy, khi task khác thay đổi tệp dùng chung, task đầu tiên có thể bị chạy lại do output snapshot đã thay đổi. Vấn đề là hai task vẫn đang tranh quyền ghi cùng một sản phẩm: kết quả cuối phụ thuộc vào task nào ghi sau cùng, và việc chạy lại hoặc khôi phục cache của một task có thể thay thế nội dung mà task kia cần. Đây là trạng thái khó dự đoán và khó bảo đảm đúng qua các lần build.

Đầu ra chồng lấn cũng làm giảm khả năng suy luận về cache và tính song song. Việc khai báo output không chính xác hoặc nhiều task cùng sở hữu một vùng tệp khiến build khó xác định tác vụ nào chịu trách nhiệm đối với nội dung hiện có.

## 4. Ví dụ thiết kế sai trong Gradle

Đoạn build script dưới đây minh họa hai task cùng khai báo và ghi một tệp:

```groovy
def sharedConfig = layout.buildDirectory.file('generated/config/app.properties')

tasks.register('generateDevConfig') {
    outputs.file(sharedConfig)

    doLast {
        def output = sharedConfig.get().asFile
        output.parentFile.mkdirs()
        output.setText('environment=dev\n', 'UTF-8')
    }
}

tasks.register('generateProdConfig') {
    outputs.file(sharedConfig)

    doLast {
        def output = sharedConfig.get().asFile
        output.parentFile.mkdirs()
        output.setText('environment=prod\n', 'UTF-8')
    }
}
```

`generateDevConfig` và `generateProdConfig` cùng nhận quyền ghi `app.properties`. Chạy riêng từng task có thể cho kết quả có vẻ đúng. Khi cả hai được đưa vào cùng một build, kết quả phụ thuộc vào thứ tự và cách thực thi.

Thêm `dependsOn` hoặc `mustRunAfter` giữa hai task chỉ có thể làm rõ một phần quan hệ thực thi; nó không giải quyết mâu thuẫn về nội dung. Nếu hai tác vụ đều được thiết kế để tạo ra hai cấu hình khác nhau, chúng cần hai đường dẫn đầu ra khác nhau.

## 5. Cách 1: mỗi tác vụ sở hữu một đầu ra riêng

Giải pháp trực tiếp là cấp cho từng task một tệp hoặc thư mục riêng.

```groovy
def devConfig = layout.buildDirectory.file('generated/config/dev.properties')
def prodConfig = layout.buildDirectory.file('generated/config/prod.properties')

tasks.register('generateDevConfig') {
    inputs.property('environment', 'dev')
    outputs.file(devConfig)

    doLast {
        def output = devConfig.get().asFile
        output.parentFile.mkdirs()
        output.setText('environment=dev\n', 'UTF-8')
    }
}

tasks.register('generateProdConfig') {
    inputs.property('environment', 'prod')
    outputs.file(prodConfig)

    doLast {
        def output = prodConfig.get().asFile
        output.parentFile.mkdirs()
        output.setText('environment=prod\n', 'UTF-8')
    }
}
```

Kết quả:

```text
build/
└── generated/
    └── config/
        ├── dev.properties
        └── prod.properties
```

Hai task không còn ghi cùng một tệp. Chúng có thể được thực thi độc lập hoặc song song nếu không có quan hệ phụ thuộc nào khác. Gradle cũng có thể theo dõi riêng đầu ra của từng task.

Trong ví dụ này, `inputs.property(...)` khai báo giá trị môi trường ảnh hưởng đến kết quả. Nếu giá trị đó thay đổi, Gradle có thông tin để xem xét chạy lại task. Với một task thực tế, cần khai báo tất cả đầu vào ảnh hưởng đến nội dung, chẳng hạn template, schema, phiên bản generator hoặc tùy chọn build.

## 6. Cách 2: dùng một tác vụ duy nhất để tạo tệp dùng chung

Đôi khi nhiều bước cần đóng góp dữ liệu vào cùng một tệp cuối cùng. Nếu sản phẩm cuối là một tệp duy nhất, hãy tập trung quyền ghi vào một task tổng hợp.

```text
generateDevConfig  ---> dev.properties --+
                                         |
generateProdConfig ---> prod.properties -+---> collectConfigs
                                                   |
                                                   v
                                         distribution/config/...
```

Hai task tạo dữ liệu riêng. Task `collectConfigs` chỉ đọc các tệp đó và sở hữu thư mục kết quả tổng hợp.

```groovy
def devConfig = layout.buildDirectory.file('generated/config/dev.properties')
def prodConfig = layout.buildDirectory.file('generated/config/prod.properties')

tasks.register('generateDevConfig') {
    outputs.file(devConfig)

    doLast {
        def output = devConfig.get().asFile
        output.parentFile.mkdirs()
        output.setText('environment=dev\n', 'UTF-8')
    }
}

tasks.register('generateProdConfig') {
    outputs.file(prodConfig)

    doLast {
        def output = prodConfig.get().asFile
        output.parentFile.mkdirs()
        output.setText('environment=prod\n', 'UTF-8')
    }
}

tasks.register('collectConfigs', Sync) {
    dependsOn 'generateDevConfig', 'generateProdConfig'
    from(devConfig, prodConfig)
    into(layout.buildDirectory.dir('distribution/config'))
}
```

`collectConfigs` là tác vụ duy nhất ghi vào `build/distribution/config`. Nó không sửa hai tệp nguồn mà các task sinh cấu hình đã tạo. Nếu cần biến đổi nội dung hoặc hợp nhất chúng thành một tệp, có thể dùng một custom task thay cho `Sync`; custom task đó sẽ khai báo hai tệp nguồn là input và tệp hợp nhất là output.

Điểm quan trọng là quyền ghi được tập trung ở đúng bước tạo sản phẩm cuối. Các task thành phần chỉ tạo đầu ra riêng, còn task tổng hợp có trách nhiệm kết hợp chúng.

## 7. Cách 3: chia thư mục đầu ra theo tác vụ

Với task sinh nhiều tệp, khai báo một thư mục đầu ra riêng cho từng task thường dễ quản lý hơn việc đặt mọi tệp vào cùng một thư mục chung.

```text
build/generated/
├── openApiClient/
│   └── java/...
├── databaseModel/
│   └── java/...
└── messageTypes/
    └── java/...
```

Ví dụ:

```groovy
def openApiOutput = layout.buildDirectory.dir('generated/openApiClient')
def modelOutput = layout.buildDirectory.dir('generated/databaseModel')

tasks.register('generateOpenApiClient') {
    outputs.dir(openApiOutput)
    // Generator chỉ ghi tệp thuộc openApiOutput.
}

tasks.register('generateDatabaseModel') {
    outputs.dir(modelOutput)
    // Generator chỉ ghi tệp thuộc modelOutput.
}
```

Mỗi task sở hữu một cây thư mục riêng. Điều này làm cho việc dọn đầu ra cũ, kiểm tra kết quả, cache và đăng ký source directory rõ ràng hơn.

Không nên khai báo cả `build/generated` là output directory của nhiều task chỉ vì chúng đều ghi một vài tệp con bên trong. Một output directory là một vùng đầu ra mà task chịu trách nhiệm quản lý. Nếu hai task cùng khai báo thư mục cha hoặc các vùng thư mục chồng lấn, ranh giới sở hữu trở nên mơ hồ.

## 8. Đầu ra được sinh và tác vụ tiêu thụ

Một task tiêu thụ nên nhận đầu ra thông qua quan hệ dữ liệu được khai báo trong build model. Điều này giúp build tool biết task nào phải chạy trước task nào.

Ví dụ, task sinh mã Java tạo ra thư mục riêng:

```groovy
def generatedJava = layout.buildDirectory.dir('generated/sources/model')

tasks.register('generateModel') {
    outputs.dir(generatedJava)

    doLast {
        def root = generatedJava.get().asFile
        def packageDir = new File(root, 'com/example/model')
        packageDir.mkdirs()
        new File(packageDir, 'Product.java').setText('''
package com.example.model;

public class Product {
    private String name;
}
'''.stripIndent(), 'UTF-8')
    }
}

sourceSets.main.java.srcDir(generatedJava)

tasks.named('compileJava') {
    dependsOn tasks.named('generateModel')
}
```

`generateModel` sở hữu cây thư mục `build/generated/sources/model`. `compileJava` sử dụng thư mục đó làm một source directory và phụ thuộc vào task sinh mã. Khi biên dịch, Gradle biết cần chạy generator trước.

Đối với các build logic phức tạp hơn, nên dùng `Provider`, `Property`, `DirectoryProperty`, `RegularFileProperty` và `TaskProvider` để nối đầu ra của task sản xuất với đầu vào của task tiêu thụ. Cách nối provider giúp giữ thông tin về nguồn gốc dữ liệu và tránh tự ghép đường dẫn rời rạc trong nhiều nơi.

Một task tiêu thụ thường chỉ cần khai báo hoặc nhận input từ đầu ra của producer. Nó không nên sửa trực tiếp tệp mà producer tạo. Nếu cần một biến thể đã biến đổi, hãy tạo một output path mới do task biến đổi sở hữu.

## 9. Phân biệt dependsOn và các quy tắc thứ tự

Trong Gradle, cần hiểu rõ các quan hệ task:

### `dependsOn`

```groovy
tasks.register('packageApplication') {
    dependsOn tasks.named('compileJava')
}
```

`dependsOn` đưa task phụ thuộc vào task graph. Khi `packageApplication` được yêu cầu, Gradle cũng cần thực thi `compileJava` nếu task đó chưa có kết quả phù hợp.

Đây là quan hệ phù hợp khi task B cần đầu ra do task A tạo ra. Tuy nhiên, nếu hai task A và B cùng ghi một tệp, chỉ thêm dependency giữa chúng không làm cho thiết kế trở nên đúng. Nó chỉ quy định thứ tự; tác vụ chạy sau vẫn có thể ghi đè kết quả của tác vụ trước.

### `mustRunAfter`

```groovy
tasks.named('taskB') {
    mustRunAfter tasks.named('taskA')
}
```

`mustRunAfter` quy định thứ tự nếu cả hai task đều đã được đưa vào task graph. Nó không tự đưa `taskA` vào graph khi chỉ yêu cầu `taskB`.

Quy tắc thứ tự có thể hữu ích khi hai công việc độc lập cần chạy theo trình tự vì lý do khác, nhưng không nên dùng nó để che giấu việc nhiều task cùng sở hữu một output. Nếu output cần được tạo một lần, hãy thiết kế một producer duy nhất.

### `shouldRunAfter` và `finalizedBy`

`shouldRunAfter` là quy tắc thứ tự mềm; Gradle có thể không tuân theo trong một số tình huống cần phá vỡ chu trình hoặc tối ưu thực thi. `finalizedBy` chỉ định task finalizer chạy sau task được finalize trong những điều kiện phù hợp. Cả hai đều không chuyển quyền sở hữu output từ task này sang task khác.

Hãy chọn quan hệ theo đúng ý nghĩa: dependency biểu diễn dữ liệu cần có, ordering biểu diễn thứ tự, còn output declaration biểu diễn trách nhiệm tạo dữ liệu.

## 10. Tác vụ tổng hợp và hợp nhất dữ liệu

Không phải lúc nào cũng có thể tránh việc nhiều nguồn đóng góp vào một kết quả. Ví dụ:

- Nhiều module tạo metadata để ghép thành catalog.
- Nhiều file schema được chuyển thành một tài liệu tổng hợp.
- Nhiều báo cáo kiểm thử được ghép thành một báo cáo duy nhất.
- Nhiều tệp cấu hình thành phần được kết hợp thành cấu hình phát hành.

Mô hình an toàn là **nhiều producer, nhiều đầu ra riêng, một aggregator sở hữu kết quả hợp nhất**.

```text
producer A ---> output/A.json --+
                               |
producer B ---> output/B.json --+---> aggregateCatalog ---> catalog.json
                               |
producer C ---> output/C.json --+
```

Aggregator cần khai báo tất cả đầu ra thành phần là input và khai báo tệp kết quả cuối là output. Quy tắc hợp nhất phải xác định được:

1. Thứ tự đọc các nguồn.
2. Cách xử lý bản ghi trùng khóa.
3. Cách xử lý dữ liệu thiếu hoặc không hợp lệ.
4. Cách mã hóa và định dạng đầu ra.
5. Cách bảo đảm kết quả giống nhau khi đầu vào giống nhau.

Nếu không quy định các điểm này, aggregator có thể tạo ra kết quả khác nhau theo thứ tự duyệt tệp hoặc thứ tự hoàn thành của các producer.

Ví dụ, nếu ba file JSON chứa các module, aggregator nên sắp xếp module theo khóa ổn định trước khi serialize. Nếu hai nguồn cùng định nghĩa một module id, phải có quy tắc rõ ràng: báo lỗi, chọn nguồn ưu tiên đã được cấu hình, hoặc hợp nhất theo schema. Không nên để bản ghi được đọc cuối cùng thắng một cách ngẫu nhiên.

## 11. Khai báo output phải khớp với hành vi ghi thực tế

Khai báo output không chỉ là thông tin để Gradle hiển thị. Nó là hợp đồng giữa task và build tool.

Nếu task ghi `build/generated/config/app.properties` nhưng lại khai báo output là `build/generated/config/other.properties`, Gradle theo dõi sai tệp. Khi đầu ra thật thay đổi, trạng thái up-to-date hoặc cache có thể không phản ánh đúng.

Nếu task khai báo cả thư mục lớn nhưng chỉ thực sự quản lý một tệp nhỏ, task có thể vô tình nhận quyền sở hữu một vùng chứa đầu ra của task khác. Ngược lại, nếu task ghi nhiều tệp nhưng chỉ khai báo một tệp, các tệp phụ có thể bị bỏ sót khỏi quá trình theo dõi.

Khi thiết kế task, hãy xác định rõ:

- Đầu ra là một file hay một directory?
- Đường dẫn có ổn định giữa các lần chạy không?
- Task có ghi thêm tệp phụ, marker, log hoặc metadata không?
- Tệp nào là output thật, tệp nào chỉ là file tạm?
- Có task khác đang khai báo cùng file hoặc directory không?

Với custom task Gradle, các property `@OutputFile`, `@OutputDirectory` và các property input tương ứng giúp hợp đồng được thể hiện rõ trong lớp task. Chỉ khai báo những đầu ra mà task thực sự chịu trách nhiệm quản lý.

## 12. Không ghi đầu ra build vào thư mục mã nguồn

Một nguồn xung đột khác là để task ghi trực tiếp vào `src/main/java`, `src/main/resources` hoặc các thư mục chứa nội dung do con người quản lý.

Ví dụ không nên làm:

```groovy
tasks.register('generateVersionInfo') {
    doLast {
        file('src/main/resources/version.properties').text = 'version=1.0'
    }
}
```

Task này thay đổi một tệp nằm trong cây mã nguồn. Hậu quả có thể gồm:

- Build làm thay đổi working tree dù người dùng chỉ muốn biên dịch.
- Tệp được sinh ghi đè nội dung do lập trình viên chỉnh sửa.
- Hai build hoặc hai cấu hình môi trường cùng cập nhật một tệp nguồn.
- Kết quả phụ thuộc vào lần build trước và khó tái tạo từ repository sạch.

Nên đưa tệp được sinh vào `build/`:

```groovy
def versionFile = layout.buildDirectory.file('generated/resources/version.properties')

tasks.register('generateVersionInfo') {
    inputs.property('version', project.version.toString())
    outputs.file(versionFile)

    doLast {
        def output = versionFile.get().asFile
        output.parentFile.mkdirs()
        output.setText("version=${project.version}\n", 'UTF-8')
    }
}
```

Sau đó đăng ký thư mục hoặc tệp sinh làm resource input của source set, đồng thời nối quan hệ task để xử lý tài nguyên sau khi generator hoàn thành. Cây `src/` tiếp tục là nơi chứa nội dung nguồn được quản lý; cây `build/` là nơi chứa đầu ra được tạo trong quá trình build.

## 13. Xóa đầu ra cũ và tránh để lại dữ liệu mồ côi

Một task có thể tạo nhiều tệp theo dữ liệu đầu vào. Ở lần chạy sau, số lượng tệp có thể giảm. Nếu task chỉ ghi các tệp mới mà không dọn những tệp cũ đã lỗi thời, thư mục output sẽ chứa dữ liệu mồ côi.

Ví dụ lần đầu generator tạo:

```text
generated/
├── A.java
├── B.java
└── C.java
```

Sau khi schema thay đổi, chỉ còn A và B. Nếu task không loại bỏ C, compiler vẫn có thể nhìn thấy C và biên dịch một lớp không còn hợp lệ.

Task sở hữu một output directory cần có chính sách quản lý nội dung của directory đó. Một số cách thường dùng:

- Dùng output directory riêng cho task và xóa/tạo lại directory đó trước khi sinh nội dung, nếu toàn bộ directory thực sự thuộc task.
- Dùng API copy/sync có quy tắc đồng bộ rõ ràng để loại bỏ tệp đích không còn trong nguồn.
- Ghi đầu ra vào thư mục phiên bản hóa theo input fingerprint, sau đó cập nhật một bước chọn phiên bản đang hoạt động.

Không được xóa thư mục dùng chung nếu bên trong có đầu ra do task khác sở hữu. Việc dọn output chỉ an toàn khi ranh giới ownership được xác định đúng.

## 14. Ghi tệp an toàn: atomic write không thay thế ownership

Với tệp cấu hình hoặc metadata được đọc bởi tiến trình khác, có thể cần tránh để người đọc nhìn thấy nội dung đang ghi dở. Một kỹ thuật là ghi vào tệp tạm nằm cạnh tệp đích, sau đó đổi tên hoặc di chuyển tệp tạm thành tệp chính khi đã ghi xong.

```text
app.properties.tmp  -- ghi hoàn chỉnh -->  app.properties
```

Nếu filesystem hỗ trợ thao tác rename/replace nguyên tử trong cùng filesystem, người đọc thường sẽ thấy phiên bản cũ hoặc phiên bản mới hoàn chỉnh thay vì một phần nội dung đang được ghi. Cách triển khai cần xử lý trường hợp tệp tạm còn sót, lỗi ghi, quyền truy cập và khả năng atomic move của filesystem.

Tuy nhiên, atomic write chỉ giảm nguy cơ đọc phải tệp chưa hoàn chỉnh. Nó **không giải quyết xung đột giữa hai writer**. Nếu A và B cùng tạo hai tệp tạm rồi lần lượt thay thế `app.properties`, kết quả cuối vẫn phụ thuộc vào writer nào thay thế sau cùng. Quyền sở hữu một writer vẫn cần được bảo đảm.

Không nên dùng cơ chế lock như giải pháp mặc định cho task nội bộ nếu có thể thiết kế output riêng. Lock làm tăng độ phức tạp, có thể gây chờ hoặc deadlock, và vẫn cần quy tắc xác định nội dung nào được ghi. Chỉ cân nhắc lock khi nhiều tiến trình độc lập thực sự phải cập nhật một tài nguyên dùng chung mà không thể tách quyền sở hữu.

## 15. Nhiều build cùng chạy trên một workspace

Task graph của một lần chạy Gradle chỉ điều phối các task trong build đó. Hai tiến trình build độc lập chạy đồng thời trên cùng workspace có thể không chia sẻ một task graph. Nếu cả hai cùng ghi vào `build/generated/shared.json`, chúng vẫn có thể xung đột dù từng build riêng lẻ đã thiết kế một writer cho file đó.

Các biện pháp thường dùng:

- Mỗi build hoặc mỗi job CI sử dụng workspace riêng.
- Không đặt đầu ra tạm của build vào một thư mục dùng chung giữa nhiều checkout.
- Nếu cần chia sẻ artifact, publish artifact sau khi build hoàn tất và để build khác tiêu thụ một phiên bản bất biến.
- Với tài nguyên bên ngoài thật sự dùng chung, xác định giao thức đồng bộ, quyền cập nhật và chính sách xử lý lỗi rõ ràng.

Đối với Gradle, parallel project execution có thể làm lộ các xung đột vốn đã tồn tại, đặc biệt khi task thuộc những project khác nhau cùng ghi vào một thư mục dùng chung. Hai tiến trình build độc lập cũng có thể tranh chấp cùng workspace. Không nên tắt song song như cách sửa lâu dài cho hai task cùng ghi một tệp. Hãy làm rõ ownership và dependency trước; sau đó build có thể tận dụng song song ở những nhánh độc lập.

## 16. Áp dụng nguyên tắc ownership trong Maven

Maven tổ chức build theo lifecycle và các plugin goal. Mỗi plugin goal có thể đọc đầu vào và ghi ra một thư mục hoặc tệp. Cùng một nguyên tắc vẫn áp dụng: mỗi đường dẫn đầu ra nên có một goal chịu trách nhiệm tạo và cập nhật.

Ví dụ, hai lần chạy generator cho hai môi trường không nên cùng ghi:

```text
target/generated-config/application.properties
```

Hãy cấu hình output directory hoặc tên tệp riêng:

```text
target/generated-config/dev/application.properties
target/generated-config/prod/application.properties
```

Nếu cần tạo một tệp phát hành tổng hợp, dùng một goal hoặc plugin execution riêng làm bước tổng hợp và ghi vào đường dẫn cuối cùng. Các goal trước đó tạo đầu ra riêng và được khai báo trong lifecycle hoặc cấu hình để bước tổng hợp chạy sau chúng.

Thứ tự các plugin execution trong lifecycle có thể giúp xác định giai đoạn chạy, nhưng không thay thế việc thiết kế đầu ra không chồng lấn. Hai goal ghi cùng một tệp vẫn tạo ra phụ thuộc vào thứ tự và trạng thái trước đó.

## 17. Những lỗi thiết kế thường gặp

| Thiết kế | Rủi ro | Cách tổ chức tốt hơn |
|---|---|---|
| Hai task cùng ghi một file cấu hình | Ghi đè hoặc kết quả không xác định | Mỗi task ghi một file riêng; một task tổng hợp tạo file cuối |
| Nhiều generator ghi vào cùng output directory | Xóa nhầm hoặc ghi đè tệp của nhau | Tách directory theo generator |
| Task đọc file do task khác tạo nhưng không khai báo dependency | Có thể đọc khi producer chưa chạy hoặc đọc dữ liệu cũ | Nối output provider và dependency rõ ràng |
| Task ghi vào `src/` | Làm bẩn source tree và có thể ghi đè nội dung người dùng | Ghi vào `build/` rồi đăng ký làm input |
| Dùng `mustRunAfter` để xử lý hai writer | Chỉ sắp xếp, không giải quyết quyền sở hữu | Chuyển thành một writer hoặc các output riêng |
| Khai báo output không đúng đường dẫn thật | Up-to-date/cache không phản ánh đúng dữ liệu | Khai báo toàn bộ output thực tế và chỉ output task quản lý |
| Xóa thư mục output dùng chung | Xóa dữ liệu do task khác tạo | Mỗi task sở hữu một vùng riêng trước khi dọn |
| Dùng append vào cùng tệp ở mỗi lần build | Dữ liệu bị lặp, phụ thuộc lần chạy trước | Tạo nội dung xác định từ input và ghi thay thế |
| Dựa vào atomic rename để cho nhiều writer | Vẫn có writer thắng cuối cùng | Một writer; atomic write chỉ là bảo vệ bổ sung |

## 18. Cách thiết kế một task có quyền sở hữu đầu ra rõ ràng

Khi tạo custom task, hãy xác định hợp đồng trước khi viết phần xử lý:

1. **Đầu vào:** những tệp, thuộc tính và tùy chọn nào ảnh hưởng đến kết quả?
2. **Đầu ra:** task tạo chính xác tệp hoặc thư mục nào?
3. **Chủ sở hữu:** có task hoặc tiến trình nào khác ghi vào cùng vùng đầu ra không?
4. **Dependency:** task nào phải chạy trước để cung cấp input?
5. **Tính xác định:** cùng đầu vào có tạo cùng nội dung không?
6. **Dọn dữ liệu cũ:** khi input giảm hoặc thay đổi, tệp lỗi thời được xử lý thế nào?
7. **Lỗi giữa chừng:** lần chạy thất bại có để lại tệp dở dang hoặc trạng thái khiến lần sau hiểu sai không?

Với Gradle, một custom task có thể biểu diễn hợp đồng qua property được đánh dấu input/output. Ví dụ khung task:

```groovy
abstract class GenerateNotice extends DefaultTask {
    @Input
    abstract Property<String> getMessage()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        File output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.setText(message.get() + '\n', 'UTF-8')
    }
}

tasks.register('generateNotice', GenerateNotice) {
    message = 'Build completed'
    outputFile = layout.buildDirectory.file('generated/notice.txt')
}
```

Task `generateNotice` khai báo một input property và một output file. Đường dẫn output được cấu hình từ build directory. Task chỉ ghi tệp `notice.txt` mà nó sở hữu.

Trong dự án lớn, nên đặt lớp task trong build logic hoặc convention plugin dùng chung thay vì khai báo nhiều class phức tạp trong build file của từng module. Dù cách tổ chức code khác nhau, hợp đồng input/output và nguyên tắc một writer vẫn giữ nguyên.

## 19. Ví dụ lần theo một lỗi output bị ghi đè

Giả sử build đôi khi đóng gói cấu hình `dev`, đôi khi lại đóng gói cấu hình `prod`, dù lệnh build không thay đổi.

Một cách điều tra hợp lý:

**Bước 1: tìm đường dẫn tệp cuối.** Xác định chính xác JAR đang chứa tệp nào và tệp đó được lấy từ thư mục trung gian nào.

**Bước 2: tìm mọi nơi ghi tệp.** Tìm các task, plugin execution hoặc script có thao tác ghi vào đường dẫn đó. Bao gồm cả task ghi cả thư mục cha chứa tệp.

**Bước 3: đối chiếu khai báo output.** Xem task nào khai báo `outputs.file`, `outputs.dir`, `@OutputFile` hoặc `@OutputDirectory` trỏ đến cùng vùng.

**Bước 4: xem task graph.** Xác định các writer có thể chạy cùng build, quan hệ `dependsOn` và quy tắc thứ tự hiện tại. Nếu hai task không có dependency, chúng có thể được xem là độc lập.

**Bước 5: xác định ý nghĩa dữ liệu.** Nếu hai task đại diện cho hai môi trường, chúng cần hai output riêng. Nếu cả hai là nguồn của một file cuối, cần task tổng hợp với quy tắc hợp nhất.

**Bước 6: sửa ownership.** Chuyển mỗi producer về thư mục riêng, khai báo output chính xác và để một task duy nhất tạo artifact cuối.

**Bước 7: kiểm tra từ trạng thái sạch và incremental.** Chạy build sau khi xóa output theo đúng phạm vi, sau đó chạy lại không thay đổi input. Kết quả cần ổn định ở cả lần đầu và lần chạy tiếp theo.

Không nên chỉ thêm một khoảng chờ hoặc sắp xếp task theo thứ tự đang cho kết quả đúng. Cách đó có thể làm lỗi khó tái hiện hơn mà không sửa nguyên nhân là nhiều writer cùng sở hữu một tệp.

## 20. Checklist khi đọc hoặc thiết kế task graph

Khi xem một build có nhiều tác vụ tạo đầu ra, hãy đặt các câu hỏi sau:

- Mỗi output file hoặc output directory có một owner rõ ràng không?
- Có hai task khai báo cùng một file hoặc các directory chồng lấn không?
- Task tiêu thụ có dependency tới producer không?
- Output provider có được truyền trực tiếp giữa các task hay đường dẫn bị sao chép thủ công ở nhiều nơi?
- Tác vụ tổng hợp có phải writer duy nhất của sản phẩm cuối không?
- Task có ghi vào source tree hoặc thư mục dùng chung ngoài phạm vi của nó không?
- Output declaration có khớp toàn bộ tệp thực tế được tạo không?
- Dữ liệu cũ có được dọn trong phạm vi ownership của task không?
- Hai build độc lập có thể cùng ghi vào workspace hoặc thư mục dùng chung không?
- Kết quả có xác định và ổn định khi bật parallel execution hoặc chạy incremental không?

Một build được thiết kế tốt có thể cho biết đầu ra nào đến từ tác vụ nào, tác vụ nào cần chạy trước, và ai chịu trách nhiệm cập nhật tệp khi đầu vào thay đổi. Khi mỗi đầu ra có một chủ sở hữu rõ ràng, các tác vụ độc lập có thể chạy song song mà không tranh chấp tệp, còn các bước tổng hợp có thể kết hợp dữ liệu theo một quy tắc duy nhất và có thể tái tạo.
