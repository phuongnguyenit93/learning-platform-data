# Loại trừ phụ thuộc bắc cầu: lý do và rủi ro

Trong Gradle, một dependency có thể kéo theo nhiều dependency khác. Những thư viện được thêm vào theo cách đó gọi là **phụ thuộc bắc cầu** (transitive dependencies). Chúng giúp ứng dụng sử dụng thư viện mà không phải tự khai báo mọi thành phần nền tảng, nhưng đôi khi một dependency bắc cầu không phù hợp với ứng dụng: nó trùng chức năng với thư viện khác, gây xung đột, không cần thiết, hoặc cần được thay bằng một phiên bản đã được kiểm soát.

Gradle cho phép loại trừ dependency bắc cầu bằng quy tắc **exclude**. Tuy nhiên, loại trừ một module khỏi một nhánh dependency không nhất thiết loại bỏ module đó khỏi toàn bộ graph. Nếu một nhánh khác vẫn cần module ấy, nó có thể tiếp tục xuất hiện. Loại trừ quá rộng còn có thể làm thiếu lớp ở thời điểm biên dịch hoặc chạy chương trình.

## 1. Phụ thuộc bắc cầu hình thành như thế nào?

Giả sử ứng dụng khai báo thư viện A. Thư viện A lại cần thư viện B để hoạt động. Khi Gradle phân giải dependency, B được đưa vào graph dù build script của ứng dụng không khai báo trực tiếp B.

~~~text
Ứng dụng
└── thư viện A
    └── thư viện B
~~~

Trong ví dụ này:

- **Ứng dụng** khai báo A như dependency trực tiếp.
- **Thư viện A** khai báo B trong metadata của nó.
- **Thư viện B** là dependency bắc cầu của ứng dụng.

Một thư viện có thể có nhiều dependency bắc cầu, và mỗi dependency đó lại có thể kéo theo các module khác. Vì vậy, một khai báo ngắn trong build script có thể tạo ra một graph khá lớn.

Ví dụ Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.example:library-a:1.0.0")
}
~~~

Nếu metadata của **library-a** khai báo phụ thuộc vào **org.example:library-b:2.0.0**, Gradle sẽ xem xét và phân giải B khi xây dựng classpath của configuration phù hợp.

Dependency bắc cầu thường cần thiết. Không nên mặc định rằng mọi dependency không xuất hiện trực tiếp trong build script đều có thể loại bỏ. Trước khi thêm exclude, hãy xác định thư viện nào khai báo dependency đó và thành phần nào thực sự sử dụng nó.

## 2. Khi nào nên loại trừ dependency bắc cầu?

Một số lý do có thể hợp lý:

### Tránh một thành phần không mong muốn hoặc không cần thiết

Một thư viện có thể khai báo thêm adapter, integration hoặc provider mà ứng dụng không sử dụng. Nếu đã xác nhận thành phần đó không cần thiết trong các đường chạy của ứng dụng, có thể loại trừ để giảm dependency graph.

### Tránh nạp nhiều implementation cho cùng một chức năng

Ví dụ, ứng dụng có thể dùng một logging backend nhưng một thư viện kéo thêm backend khác. Nhiều binding hoặc provider cùng lúc có thể gây cảnh báo, lựa chọn backend không như mong đợi hoặc hành vi khó đoán. Khi đã xác định backend chuẩn của ứng dụng, có thể loại bỏ adapter không phù hợp và khai báo đúng implementation cần dùng.

### Thay dependency bắc cầu bằng dependency được quản lý riêng

Một thư viện cũ có thể kéo theo module mà ứng dụng muốn thay bằng phiên bản đã được phê duyệt. Trong trường hợp đó, nhóm có thể loại trừ dependency từ nhánh gây ra nó rồi khai báo dependency thay thế hoặc đặt constraint để Gradle chọn phiên bản phù hợp.

Cần nhớ rằng **exclude không tự thêm thư viện thay thế**. Nếu ứng dụng hoặc thư viện vẫn cần API đó, phải cung cấp một dependency tương thích theo cách khác.

### Giảm thành phần không cần thiết trong môi trường triển khai

Một số dependency có thể chỉ phục vụ integration không dùng trong ứng dụng, hoặc chứa thành phần không cần trong môi trường triển khai cụ thể. Việc loại bỏ có thể giảm kích thước classpath hoặc số artifact cần phân phối, nhưng phải kiểm tra cả đường chạy, reflection, service provider và cấu hình runtime.

### Xử lý dependency không tương thích

Một dependency bắc cầu có thể gây xung đột với kiến trúc hoặc chính sách của ứng dụng. Exclude có thể là một phần của giải pháp khi nhóm đã xác định module đó không cần thiết hoặc đã có thành phần thay thế tương thích.

Nếu vấn đề thực chất là **phiên bản** của module không phù hợp, hãy cân nhắc constraint, platform hoặc dependency management để chọn phiên bản đúng. Exclude toàn bộ module có thể loại bỏ cả API cần thiết.

## 3. Exclude theo một dependency cụ thể

Cách thường dùng là thêm quy tắc exclude ngay trong khai báo dependency đã kéo theo module không mong muốn.

Ví dụ Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.example:library-a:1.0.0") {
        exclude(
            group = "org.example",
            module = "legacy-adapter"
        )
    }
}
~~~

Ví dụ Groovy DSL:

~~~groovy
dependencies {
    implementation('com.example:library-a:1.0.0') {
        exclude group: 'org.example', module: 'legacy-adapter'
    }
}
~~~

Quy tắc này yêu cầu Gradle loại module **org.example:legacy-adapter** khỏi nhánh dependency do **library-a** đưa vào configuration đó.

Hai thông tin dùng để nhận diện module:

- **group** là group ID của module.
- **module** là tên module hoặc artifact.

Không cần chỉ định version trong exclude. Quy tắc nhận diện theo group và module, vì vậy nó có thể loại các phiên bản của module đó trên nhánh bị áp dụng.

Có thể chỉ định một trong hai thuộc tính nếu cần, nhưng nên chỉ rõ cả group và module để phạm vi loại trừ chính xác hơn:

~~~kotlin
dependencies {
    implementation("com.example:library-a:1.0.0") {
        exclude(group = "org.example", module = "legacy-adapter")
    }
}
~~~

Sau khi thêm exclude, hãy kiểm tra graph thực tế để xác nhận module đã biến mất khỏi configuration mục tiêu và ứng dụng vẫn hoạt động.

## 4. Loại trừ nhiều dependency bắc cầu

Một dependency có thể kéo theo nhiều module không mong muốn. Có thể thêm nhiều quy tắc exclude trong cùng một khai báo:

~~~kotlin
dependencies {
    implementation("com.example:library-a:1.0.0") {
        exclude(group = "org.example", module = "legacy-adapter")
        exclude(group = "org.example", module = "old-logging")
    }
}
~~~

Groovy DSL:

~~~groovy
dependencies {
    implementation('com.example:library-a:1.0.0') {
        exclude group: 'org.example', module: 'legacy-adapter'
        exclude group: 'org.example', module: 'old-logging'
    }
}
~~~

Chỉ thêm những quy tắc đã có lý do rõ ràng. Nếu loại trừ nhiều module cùng lúc, khi build hỏng sẽ khó xác định module nào là nguyên nhân. Có thể thay đổi từng quy tắc, quan sát graph và chạy kiểm thử sau mỗi thay đổi.

## 5. Loại trừ ở cấp configuration

Gradle cũng cho phép đặt exclude rule trên một configuration. Khi đó, quy tắc có phạm vi rộng hơn và được áp dụng cho các dependency thuộc configuration đó.

Ví dụ Kotlin DSL:

~~~kotlin
configurations.configureEach {
    exclude(
        group = "org.example",
        module = "legacy-adapter"
    )
}
~~~

Ví dụ Groovy DSL:

~~~groovy
configurations.configureEach {
    exclude group: 'org.example', module: 'legacy-adapter'
}
~~~

Cách này hữu ích khi nhóm có chính sách chung và muốn loại module khỏi nhiều dependency trong configuration. Tuy nhiên, nó có thể ảnh hưởng đến các nhánh dependency khác mà người viết build script không nghĩ tới.

Nếu chỉ một thư viện cụ thể kéo theo module không mong muốn, nên bắt đầu bằng exclude trên dependency đó. Dùng exclude cấp configuration khi thực sự muốn áp dụng quy tắc rộng cho configuration tương ứng và đã kiểm tra tác động.

Cần xác định rõ configuration nào đang bị ảnh hưởng. Ví dụ, **compileClasspath**, **runtimeClasspath**, **testCompileClasspath** và **testRuntimeClasspath** phục vụ các mục đích khác nhau. Một thay đổi có thể làm dependency biến mất ở configuration này nhưng vẫn xuất hiện ở configuration khác.

## 6. Vì sao exclude ở một nhánh nhưng module vẫn xuất hiện?

Đây là đặc điểm quan trọng của dependency graph. Exclude trên một dependency áp dụng cho nhánh mà dependency đó đưa vào. Nếu module vẫn được yêu cầu thông qua một đường khác, Gradle có thể giữ module trong graph.

Giả sử graph ban đầu như sau:

~~~text
Ứng dụng
├── thư viện A
│   └── logging-api
└── thư viện B
    └── logging-api
~~~

Ứng dụng thêm exclude trên A:

~~~kotlin
dependencies {
    implementation("com.example:library-a:1.0.0") {
        exclude(group = "org.example", module = "logging-api")
    }

    implementation("com.example:library-b:1.0.0")
}
~~~

Nhánh từ A không còn đưa **logging-api** vào graph, nhưng nhánh từ B vẫn yêu cầu module này:

~~~text
Ứng dụng
├── thư viện A
│   └── logging-api  [excluded on this path]
└── thư viện B
    └── logging-api  [still requested]
~~~

Vì vậy, **logging-api** vẫn có thể xuất hiện trong classpath.

Nếu thật sự muốn loại module khỏi configuration, cần xác định tất cả các đường đưa module vào graph và áp dụng quy tắc phù hợp trên các đường đó, hoặc dùng exclude ở cấp configuration nếu chính sách yêu cầu loại bỏ trên toàn configuration. Trước khi làm vậy, phải xác nhận không có thành phần nào cần module đó.

Một dependency được khai báo trực tiếp ở nơi khác cũng không bị quy tắc exclude gắn với một dependency cụ thể tự động xóa bỏ. Ví dụ, nếu ứng dụng tự khai báo **logging-api** như dependency trực tiếp, exclude trong **library-a** không thay thế hoặc hủy khai báo trực tiếp đó.

## 7. Exclude khác gì với tắt toàn bộ dependency bắc cầu?

Có một cách khác để hạn chế dependency bắc cầu: đặt **transitive = false** cho một dependency. Cách này khác với exclude một module cụ thể.

Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.example:library-a:1.0.0") {
        isTransitive = false
    }
}
~~~

Groovy DSL:

~~~groovy
dependencies {
    implementation('com.example:library-a:1.0.0') {
        transitive = false
    }
}
~~~

Khi đó Gradle không đưa các dependency bắc cầu của **library-a** vào graph thông qua dependency declaration này.

So sánh:

| Cách | Phạm vi tác động | Khi nên cân nhắc |
|---|---|---|
| **exclude(group, module)** | Loại module được chỉ định khỏi nhánh dependency áp dụng quy tắc | Chỉ một hoặc vài dependency bắc cầu không cần thiết |
| **configuration exclude** | Loại module khỏi phạm vi configuration được cấu hình | Có chính sách chung cho configuration |
| **transitive = false** | Không lấy toàn bộ dependency bắc cầu của dependency đó | Nhóm tự quản lý đầy đủ các dependency cần thiết |

Không nên dùng **transitive = false** chỉ để xử lý một thư viện gây xung đột nếu các dependency còn lại của thư viện vẫn cần thiết. Cách này có thể khiến nhiều lớp bị thiếu và tạo ra lỗi khó truy nguyên.

## 8. Exclude không phải là cách nâng cấp một dependency

Giả sử **library-a** kéo theo **org.example:shared:1.2.0**, nhưng ứng dụng muốn dùng **shared:1.5.0**.

Một cách làm dễ gây hiểu nhầm là loại **shared** khỏi nhánh của A rồi cho rằng Gradle sẽ tự tìm một bản thay thế. Thực tế, exclude chỉ loại module khỏi nhánh đó; nó không tự tạo ra dependency mới.

Nếu ứng dụng vẫn cần module **shared**, có thể khai báo dependency trực tiếp với phiên bản mong muốn:

~~~kotlin
dependencies {
    implementation("com.example:library-a:1.0.0") {
        exclude(group = "org.example", module = "shared")
    }

    implementation("org.example:shared:1.5.0")
}
~~~

Tuy nhiên, cách này chỉ phù hợp khi phiên bản mới tương thích với **library-a**. Hãy kiểm tra API mà A sử dụng và chạy kiểm thử. Trong nhiều trường hợp, không cần exclude: chỉ cần khai báo version constraint hoặc dùng platform để Gradle chọn phiên bản tương thích.

Ví dụ constraint:

~~~kotlin
dependencies {
    implementation("com.example:library-a:1.0.0")

    constraints {
        implementation("org.example:shared:1.5.0") {
            because("Ứng dụng cần phiên bản shared đã được kiểm thử")
        }
    }
}
~~~

Constraint chỉ tác động khi module **shared** đã được yêu cầu trong graph. Nó không tự thêm module vào graph. Với yêu cầu nghiêm ngặt hơn, có thể dùng **strictly** trong rich version constraint, nhưng cần hiểu rằng xung đột không thỏa mãn có thể làm build thất bại.

## 9. Những rủi ro khi loại trừ dependency bắc cầu

### Thiếu lớp khi biên dịch

Nếu mã nguồn ứng dụng trực tiếp sử dụng một lớp được cung cấp bởi module đã loại trừ, compiler có thể báo lỗi như:

~~~text
package org.example.api does not exist
cannot find symbol
~~~

Nguyên nhân là lớp không còn trên compile classpath. Cần xác định module nào cung cấp lớp và quyết định có nên khai báo dependency trực tiếp hay không.

### Thiếu lớp khi chạy

Một số dependency chỉ được dùng khi thực thi. Ứng dụng có thể biên dịch thành công nhưng thất bại khi chạy với lỗi:

~~~text
java.lang.NoClassDefFoundError
java.lang.ClassNotFoundException
~~~

Điều này thường xảy ra khi thư viện chỉ nạp lớp ở một nhánh chức năng ít được chạy trong kiểm thử thông thường, hoặc dùng reflection để nạp lớp theo tên.

### Không tương thích ở thời điểm liên kết

Ngay cả khi đã thay bằng một module khác, API hoặc ABI có thể không tương thích. Lỗi có thể xuất hiện dưới dạng:

~~~text
java.lang.NoSuchMethodError
java.lang.AbstractMethodError
java.lang.NoSuchFieldError
~~~

Những lỗi này thường cho thấy bytecode được biên dịch dựa trên một API khác với API thực tế có trong runtime. Việc thay dependency phải dựa trên tương thích phiên bản, không chỉ dựa trên việc tên module giống nhau.

### Mất service provider hoặc integration

Một thư viện có thể được phát hiện thông qua Java Service Provider Interface (SPI), file metadata trong JAR hoặc cấu hình framework. Loại module cung cấp provider có thể khiến chức năng không hoạt động dù ứng dụng không trực tiếp import lớp của module đó.

Ví dụ, một driver, logging backend, serializer, plugin hoặc provider có thể được framework phát hiện lúc chạy. Kiểm thử compile thành công không đủ để xác nhận những integration này vẫn hoạt động.

### Quy tắc loại trừ bị bỏ qua bởi một đường dependency khác

Nếu chỉ exclude ở một dependency nhưng module vẫn được yêu cầu qua nhánh khác, module tiếp tục xuất hiện. Điều này khiến người phát triển tưởng đã loại bỏ được dependency nhưng classpath thực tế vẫn chứa nó.

### Ảnh hưởng ngoài phạm vi dự định

Exclude ở cấp configuration có thể ảnh hưởng đến nhiều thư viện khác nhau. Một module vốn không được dùng bởi A nhưng lại cần cho B hoặc test runtime có thể bị loại bỏ ngoài ý muốn.

### Khó bảo trì khi metadata thư viện thay đổi

Một thư viện được nâng cấp có thể thay đổi dependency graph. Exclude từng phù hợp có thể trở nên không cần thiết, hoặc ngược lại một dependency mới có thể xuất hiện. Các quy tắc loại trừ cần được xem xét lại khi nâng cấp thư viện cha.

## 10. Cách điều tra dependency trước khi thêm exclude

Đừng bắt đầu bằng cách thêm nhiều quy tắc loại trừ rồi thử build. Trước tiên hãy xác định module, đường dependency và configuration bị ảnh hưởng.

### Xem cây dependency

Dùng task **dependencies** để xem toàn bộ graph của configuration:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Có thể kiểm tra classpath biên dịch:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
~~~

Hoặc classpath chạy kiểm thử:

~~~bash
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

Nếu dự án chỉ có một project, có thể bỏ prefix **:app**.

Trong cây dependency, tìm group và module cần loại trừ. Xác định những thư viện nào đưa module đó vào graph, và xem có nhiều đường dependency hay không.

### Dùng dependencyInsight để truy nguồn

Lệnh **dependencyInsight** tập trung vào một module:

~~~bash
./gradlew :app:dependencyInsight --dependency logging-api --configuration runtimeClasspath
~~~

Kết quả giúp trả lời:

- Module được yêu cầu bởi dependency nào?
- Có bao nhiêu đường dẫn dẫn đến module?
- Phiên bản nào được chọn?
- Có constraint hoặc conflict resolution nào tác động không?
- Module có còn xuất hiện trong configuration sau khi áp dụng exclude không?

Nếu module vẫn xuất hiện, hãy đọc các đường dẫn trong kết quả để xác định dependency nào còn đưa nó vào graph.

### Kiểm tra đúng configuration

Một module có thể bị loại khỏi **runtimeClasspath** nhưng vẫn xuất hiện trong **testRuntimeClasspath**, hoặc ngược lại. Hãy kiểm tra configuration đúng với lỗi đang gặp.

Ví dụ:

- Lỗi import hoặc compile thường liên quan đến **compileClasspath**.
- Lỗi thiếu lớp khi ứng dụng chạy thường liên quan đến **runtimeClasspath**.
- Lỗi chỉ xảy ra khi chạy test có thể liên quan đến **testRuntimeClasspath**.

Không kết luận rằng dependency đã được loại bỏ hoàn toàn chỉ từ kết quả của một configuration.

## 11. Quy trình an toàn khi thêm exclude

Một thay đổi exclude nên có lý do, bằng chứng và kiểm thử tương ứng.

**Bước 1: Xác định module cần loại bỏ**

Ghi lại group, module và lý do. Tránh chỉ dựa vào tên JAR hoặc một thông báo cảnh báo mà chưa tìm nguồn dependency.

**Bước 2: Tìm các đường dependency**

Chạy **dependencies** và **dependencyInsight** trên configuration bị ảnh hưởng. Xác định dependency nào đưa module vào graph và có bao nhiêu đường dẫn.

**Bước 3: Xác định module có thực sự không cần thiết không**

Kiểm tra thư viện cha có sử dụng API của module hay không. Xem xét reflection, SPI, provider, plugin, driver và cấu hình runtime. Nếu module cần thiết, hãy chọn phiên bản tương thích hoặc thay thư viện cha thay vì xóa mù quáng.

**Bước 4: Chọn phạm vi exclude nhỏ nhất**

Ưu tiên exclude trên dependency cụ thể. Chỉ dùng exclude cấp configuration khi cần loại module khỏi toàn bộ configuration và đã xác nhận phạm vi tác động.

**Bước 5: Kiểm tra graph sau thay đổi**

Chạy lại:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Và:

~~~bash
./gradlew :app:dependencyInsight --dependency logging-api --configuration runtimeClasspath
~~~

Xác nhận module có còn xuất hiện qua nhánh khác hay không.

**Bước 6: Chạy kiểm thử liên quan**

Chạy biên dịch, unit test, integration test và các bài kiểm thử khởi động hoặc gọi chức năng phụ thuộc vào thư viện đã loại trừ. Nếu ứng dụng có service provider hoặc plugin runtime, hãy kiểm tra các đường chạy đó.

**Bước 7: Ghi lại lý do**

Có thể đặt lời giải thích ngay trong build script hoặc trong ghi chú thay đổi để người bảo trì hiểu vì sao exclude tồn tại. Nếu lý do đã hết hiệu lực sau khi nâng cấp thư viện cha, hãy xem xét xóa quy tắc cũ.

## 12. Ví dụ hoàn chỉnh

Giả sử ứng dụng dùng **report-client**, thư viện này kéo theo một adapter cũ mà ứng dụng không sử dụng. Sau khi kiểm tra metadata và xác nhận adapter không cần cho các chức năng đang dùng, nhóm quyết định loại trừ module đó.

Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.example:report-client:2.1.0") {
        exclude(
            group = "com.example.integration",
            module = "legacy-adapter"
        )
    }
}
~~~

Trước thay đổi, cây dependency giả định:

~~~text
runtimeClasspath
└── com.example:report-client:2.1.0
    ├── com.example:report-core:2.1.0
    └── com.example.integration:legacy-adapter:1.0.0
~~~

Sau thay đổi, nhánh đó không còn adapter:

~~~text
runtimeClasspath
└── com.example:report-client:2.1.0
    └── com.example:report-core:2.1.0
~~~

Tuy nhiên, nếu một thư viện khác cũng phụ thuộc vào **legacy-adapter**, module có thể vẫn xuất hiện:

~~~text
runtimeClasspath
├── com.example:report-client:2.1.0
│   └── legacy-adapter  [excluded on this path]
└── com.example:other-client:1.0.0
    └── legacy-adapter  [still requested]
~~~

Khi đó cần xác định **other-client** có thực sự cần adapter không. Nếu cần, không nên loại module khỏi toàn configuration chỉ để đạt được một cây dependency ngắn hơn. Có thể nâng cấp hoặc cấu hình lại thư viện đó, chọn phiên bản khác, hoặc chấp nhận module là dependency dùng chung.

Các sơ đồ trên là ví dụ minh họa. Cây dependency thực tế phải được lấy từ lệnh Gradle trên dự án đang làm việc.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Exclude một lần sẽ xóa module khỏi toàn bộ dự án | Exclude trên dependency cụ thể có phạm vi theo nhánh; đường khác vẫn có thể đưa module vào graph |
| Module không được import trực tiếp thì có thể xóa | Framework, reflection, SPI hoặc thư viện cha có thể cần module lúc chạy |
| Exclude là cách thay version cũ bằng version mới | Exclude chỉ loại module trên nhánh; muốn thay phiên bản cần dependency, constraint hoặc platform phù hợp |
| Build biên dịch thành công chứng minh exclude an toàn | Lỗi có thể chỉ xuất hiện trong runtime hoặc một chức năng ít được kiểm thử |
| Configuration exclude luôn an toàn hơn | Quy tắc rộng có thể ảnh hưởng các dependency khác trong configuration |
| Tắt transitive dependency giống exclude một module | **transitive = false** loại toàn bộ dependency bắc cầu của dependency đó |
| Cây dependency ngắn hơn đồng nghĩa ứng dụng tốt hơn | Graph nhỏ hơn không có ý nghĩa nếu thiếu chức năng hoặc làm runtime lỗi |

## 14. Những nguyên tắc cần nhớ

- Dependency bắc cầu được đưa vào graph thông qua metadata của thư viện mà ứng dụng sử dụng.
- Dùng **exclude(group, module)** khi đã xác định một module cụ thể không cần thiết trên một nhánh dependency.
- Exclude trên một dependency không bảo đảm module biến mất khỏi mọi nhánh khác.
- Exclude cấp configuration có phạm vi rộng và cần được dùng có chủ đích.
- **transitive = false** tắt toàn bộ dependency bắc cầu của một dependency; chỉ dùng khi nhóm tự quản lý đầy đủ các thư viện cần thiết.
- Exclude không tự cung cấp dependency thay thế và không phải công cụ nâng cấp phiên bản.
- Thiếu dependency có thể gây lỗi biên dịch, lỗi nạp lớp, lỗi liên kết hoặc mất provider ở runtime.
- Dùng **dependencies** và **dependencyInsight** để truy nguồn module trước và sau thay đổi.
- Kiểm tra compile, runtime và test configurations phù hợp; chạy cả integration test khi dependency liên quan đến framework hoặc provider.
- Ghi lại lý do và xem xét lại exclude khi nâng cấp thư viện cha.

Loại trừ dependency bắc cầu là một công cụ quản lý graph hữu ích khi được dùng có căn cứ. Xác định đúng module, hiểu đường dependency và kiểm tra hành vi runtime giúp tránh tình trạng build vẫn thành công nhưng ứng dụng thiếu chức năng khi triển khai.
