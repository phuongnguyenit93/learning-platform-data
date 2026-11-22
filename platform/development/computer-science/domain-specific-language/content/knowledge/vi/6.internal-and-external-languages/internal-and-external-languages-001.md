# DSL nội bộ là gì?

**DSL nội bộ (Internal Domain-Specific Language)** là ngôn ngữ chuyên biệt theo miền được xây dựng bên trong một ngôn ngữ lập trình chủ. Nó sử dụng cú pháp, cấu trúc và cơ chế sẵn có của ngôn ngữ chủ để tạo ra cách diễn đạt phù hợp với một lĩnh vực cụ thể. Vì vậy, DSL nội bộ thường còn được gọi là **DSL nhúng (embedded DSL)**.

Ví dụ, một chương trình kiểm thử có thể dùng các cấu trúc như `describe`, `context`, `it` và `expect` để mô tả hành vi cần kiểm tra. Một tệp cấu hình xây dựng có thể dùng `plugins`, `dependencies` và `tasks` để khai báo cách xây dựng phần mềm. Người viết vẫn đang sử dụng một ngôn ngữ chủ, nhưng một tập API và quy ước được thiết kế để diễn đạt công việc chuyên biệt.

Trong chủ đề phân biệt DSL nội bộ và DSL bên ngoài, điểm cốt lõi là cách ngôn ngữ chuyên biệt được tích hợp và phân tích. DSL nội bộ dựa vào ngôn ngữ chủ; DSL bên ngoài có cú pháp riêng và thường cần bộ phân tích cú pháp riêng. Hai cách đều có thể giải quyết cùng một miền nghiệp vụ, nhưng đem lại trải nghiệm viết, kiểm tra và bảo trì khác nhau.

## 1. Khái niệm DSL nội bộ

Một DSL nội bộ là một lớp trừu tượng chuyên biệt được biểu đạt bằng các thành phần của một ngôn ngữ lập trình có sẵn. Ngôn ngữ chủ cung cấp cú pháp nền tảng như lời gọi hàm, biểu thức, khối lệnh, lambda, toán tử, kiểu dữ liệu và cơ chế module. Thư viện DSL kết hợp các thành phần đó để tạo cách viết gần với khái niệm của miền.

Ví dụ, thay vì viết nhiều câu lệnh điều kiện để mô tả quy tắc, một ứng dụng có thể cung cấp API dạng DSL:

```kotlin
rule("free-shipping") {
    whenOrder { total >= 1_000_000 }
    then { shippingFee = 0 }
}
```

Đây là cú pháp minh họa cho một DSL nội bộ trong Kotlin, không phải thư viện có sẵn. Người đọc thấy tên quy tắc, điều kiện và hành động bằng các thuật ngữ của miền. Các từ `rule`, `whenOrder` và `then` thực chất được cung cấp bởi các hàm và kiểu của chương trình chủ. Bộ xử lý DSL định nghĩa chúng có ý nghĩa gì.

DSL nội bộ thường không có một bộ ngữ pháp hoàn toàn độc lập. Trình biên dịch hoặc trình thông dịch của ngôn ngữ chủ phân tích cú pháp nền tảng trước; các hàm và đối tượng của DSL sau đó xử lý cấu trúc mà người viết tạo ra.

## 2. Vì sao gọi là “nội bộ” hoặc “nhúng”?

Từ “nội bộ” nói đến việc DSL được xây dựng bên trong cú pháp và môi trường của một ngôn ngữ chủ. Nó **không** có nghĩa DSL chỉ dùng trong nội bộ một công ty, không công khai hoặc không được người dùng bên ngoài sử dụng.

Tương tự, “nhúng” không nhất thiết có nghĩa là một đoạn mã được chèn vào giữa chương trình theo nghĩa văn bản. DSL được nhúng về mặt ngôn ngữ: các biểu thức chuyên biệt là những biểu thức hợp lệ của ngôn ngữ chủ, thường được thực hiện bằng một thư viện.

Có thể hình dung mối quan hệ như sau:

```text
Ngôn ngữ chủ (Kotlin, Ruby, Scala, Java, ...)
    |
    +-- Cú pháp và cơ chế nền tảng
    |     - hàm và phương thức
    |     - lambda / block
    |     - kiểu dữ liệu và đối tượng
    |     - toán tử và biểu thức
    |
    +-- Thư viện DSL nội bộ
          - từ vựng của miền
          - cấu trúc biểu đạt
          - quy tắc và ngữ nghĩa
          - kiểm tra và thực thi
```

Người viết DSL dùng các cấu trúc của ngôn ngữ chủ để mô tả bài toán. Thư viện DSL nhận các lời gọi đó và chuyển chúng thành hành động, cấu trúc dữ liệu hoặc biểu diễn trung gian phù hợp.

## 3. Những đặc điểm thường gặp

### 3.1. Dựa trên cú pháp của ngôn ngữ chủ

DSL nội bộ không thể tùy ý tạo mọi ký hiệu hoặc quy tắc ngữ pháp như một ngôn ngữ độc lập. Nó phải tuân theo những gì ngôn ngữ chủ cho phép. Ví dụ, một DSL nhúng trong Java thường sử dụng lời gọi phương thức, interface, lambda và method chaining; DSL trong Ruby có thể tận dụng block và cú pháp gọi phương thức linh hoạt.

Giới hạn này giúp DSL dùng lại parser, trình biên dịch, hệ thống kiểu và công cụ phát triển của ngôn ngữ chủ. Đổi lại, người thiết kế phải sáng tạo trong phạm vi cú pháp có sẵn.

### 3.2. Dùng API để tạo từ vựng miền

Các tên hàm, phương thức, kiểu và thuộc tính trở thành từ vựng của DSL. Ví dụ trong một DSL truy vấn có thể có `select`, `from`, `where`, `groupBy` và `orderBy`. Trong DSL định tuyến có thể có `route`, `path`, `get` và `authenticate`.

Chất lượng của DSL phụ thuộc nhiều vào cách đặt tên. Một API có tên kỹ thuật khó hiểu sẽ không trở thành DSL dễ đọc chỉ vì nó dùng method chaining.

### 3.3. Kết hợp lời gọi hàm, chuỗi phương thức và lambda

Các mẫu phổ biến gồm:

- **Fluent API:** nối nhiều lời gọi phương thức để biểu đạt một thao tác theo chuỗi.
- **Builder:** dùng đối tượng xây dựng để mô tả cấu trúc phức tạp qua các bước khai báo.
- **Lambda hoặc block:** nhóm các biểu thức liên quan thành một khối có ngữ cảnh.
- **Extension function hoặc method extension:** bổ sung cách diễn đạt thuận tiện mà không phải thay đổi kiểu gốc, nếu ngôn ngữ hỗ trợ.
- **Operator overloading:** định nghĩa ý nghĩa miền cho một số toán tử, khi việc dùng toán tử đó làm biểu thức dễ hiểu hơn.
- **Kiểu dữ liệu chuyên biệt:** biểu diễn khái niệm miền và giới hạn giá trị bằng hệ thống kiểu của ngôn ngữ chủ.

Không phải DSL nào cũng cần tất cả các kỹ thuật này. Chúng là công cụ để tạo trải nghiệm biểu đạt, cần được chọn theo nhu cầu của miền và đặc điểm ngôn ngữ chủ.

### 3.4. Tận dụng công cụ của ngôn ngữ chủ

Vì DSL là mã hợp lệ của ngôn ngữ chủ, người phát triển thường có thể dùng IDE, trình định dạng, trình gỡ lỗi, hệ thống quản lý gói, kiểm tra kiểu và công cụ kiểm thử hiện có. Mức độ hỗ trợ cụ thể phụ thuộc vào ngôn ngữ và thiết kế thư viện.

## 4. Ví dụ quen thuộc về DSL nội bộ

### 4.1. Gradle Kotlin DSL

Gradle hỗ trợ viết cấu hình xây dựng bằng Kotlin DSL. Một phần cấu hình có thể trông như sau:

```kotlin
plugins {
    kotlin("jvm") version "2.0.0"
}

dependencies {
    implementation("org.example:library:1.0")
    testImplementation("org.example:test-library:1.0")
}

tasks.test {
    useJUnitPlatform()
}
```

Đoạn mã dùng cú pháp Kotlin, đồng thời cung cấp các khối và hàm chuyên biệt như `plugins`, `dependencies` và `tasks.test`. Người viết mô tả plugin, thư viện phụ thuộc và cách cấu hình tác vụ. Gradle cung cấp API cùng ngữ nghĩa để xử lý các khai báo đó.

### 4.2. RSpec trong Ruby

RSpec là framework kiểm thử Ruby có cú pháp DSL để mô tả hành vi:

```ruby
describe "Order" do
  context "when the order is paid" do
    it "can be shipped" do
      expect(order).to be_shippable
    end
  end
end
```

Các từ `describe`, `context`, `it` và `expect` tạo thành từ vựng gần với cách người kiểm thử mô tả yêu cầu. Chúng là các phương thức và cơ chế block trong Ruby được RSpec tổ chức thành một DSL.

### 4.3. DSL HTML trong Kotlin

Kotlin cho phép tạo các DSL dạng builder bằng lambda có receiver. Một thư viện giao diện có thể cung cấp cách viết lồng nhau như sau:

```kotlin
html {
    head {
        title { +"Trang chủ" }
    }
    body {
        h1 { +"Xin chào" }
        p { +"Đây là nội dung trang." }
    }
}
```

Đây là ví dụ minh họa phong cách Kotlin HTML DSL. Các hàm `html`, `head`, `body`, `h1` và `p` có thể xây dựng một cây phần tử HTML. Lambda có receiver giúp các hàm lồng nhau được gọi trong ngữ cảnh builder phù hợp. Dấu `+` có thể được thư viện định nghĩa để thêm nội dung văn bản vào nút hiện tại.

### 4.4. Fluent API trong Java

Java không có cú pháp block tùy biến linh hoạt như Ruby, nhưng vẫn có thể tạo DSL nội bộ bằng chuỗi lời gọi phương thức:

```java
Query query = Query.from("orders")
    .select("customer_id", "total")
    .where(eq("status", "PAID"))
    .orderBy(desc("total"));
```

Đây là ví dụ API giả định. Các phương thức `from`, `select`, `where` và `orderBy` tạo một chuỗi mô tả truy vấn. Builder có thể lưu cấu trúc truy vấn thành đối tượng trung gian, rồi chuyển nó thành SQL hoặc thực thi bằng một bộ máy khác.

Các ví dụ trên cho thấy DSL nội bộ không gắn với một ngôn ngữ cụ thể. Bất kỳ ngôn ngữ nào có cơ chế phù hợp để xây dựng API chuyên biệt đều có thể hỗ trợ một dạng DSL nhúng.

## 5. DSL nội bộ hoạt động như thế nào?

Một DSL nội bộ thường được triển khai dưới dạng thư viện. Thư viện định nghĩa các hàm, phương thức, kiểu và đối tượng mà người viết dùng để mô tả miền. Khi chương trình chạy hoặc được biên dịch, ngôn ngữ chủ xử lý cú pháp và gọi các thành phần của thư viện.

Quy trình khái quát:

1. **Người viết tạo biểu thức DSL:** gọi hàm, tạo builder, truyền lambda hoặc nối phương thức.
2. **Ngôn ngữ chủ phân tích mã:** parser của Kotlin, Ruby, Java hoặc ngôn ngữ tương ứng xác định cấu trúc chương trình.
3. **Kiểm tra của ngôn ngữ chủ:** trình biên dịch hoặc môi trường chạy kiểm tra cú pháp, tên, kiểu và các quy tắc của ngôn ngữ chủ.
4. **Thư viện DSL nhận lời gọi:** các hàm và đối tượng DSL ghi nhận cấu trúc hoặc thực hiện logic.
5. **DSL xử lý mô hình:** thư viện có thể tạo AST/đối tượng trung gian, xác thực quy tắc, sinh mã, tạo truy vấn hoặc thực thi hành động.
6. **Kết quả được sử dụng:** chương trình nhận kết quả, sinh cấu hình, chạy quy trình hoặc chuyển biểu thức sang hệ thống khác.

Ví dụ, một DSL truy vấn có thể không chạy truy vấn ngay khi gọi `where`. Thay vào đó, nó tạo một cây biểu thức gồm bảng, điều kiện và thứ tự sắp xếp. Một bước sau sẽ kiểm tra kiểu và chuyển cây đó thành SQL.

### 5.1. DSL thực thi ngay và DSL xây dựng mô hình

Có hai cách triển khai thường gặp:

- **Thực thi trực tiếp:** lời gọi DSL thực hiện hành động ngay khi được gọi. Ví dụ, một DSL tự động hóa có thể gọi API hoặc cập nhật cấu hình trong lúc chạy.
- **Xây dựng mô hình trước:** lời gọi DSL tạo một cấu trúc dữ liệu mô tả ý định; chương trình kiểm tra, tối ưu hoặc chuyển đổi cấu trúc đó rồi mới thực thi. Builder truy vấn thường dùng cách này.

Cách thứ hai giúp kiểm tra toàn bộ mô hình trước khi tạo tác động, dễ sinh tài liệu hoặc chuyển sang nhiều backend. Cách thứ nhất có thể đơn giản và trực tiếp hơn, nhưng việc dừng, xem xét hoặc biến đổi toàn bộ biểu thức có thể khó hơn.

## 6. Các kỹ thuật thiết kế DSL nội bộ

### 6.1. Fluent API và method chaining

Fluent API cho phép nối nhiều phương thức, mỗi phương thức trả về một đối tượng tiếp tục hỗ trợ thao tác tiếp theo.

```java
Report report = Report.builder()
    .forPeriod(startDate, endDate)
    .groupBy("region")
    .include("revenue")
    .sortDescending("revenue")
    .build();
```

Ví dụ này mô tả việc tạo báo cáo bằng chuỗi bước. Tên phương thức nên phản ánh ý nghĩa nghiệp vụ, và kiểu trả về có thể giới hạn những thao tác hợp lệ ở từng giai đoạn. Chẳng hạn, sau `build()` không nên tiếp tục gọi các phương thức cấu hình.

### 6.2. Builder và cấu trúc lồng nhau

Builder phù hợp khi DSL cần mô tả một cấu trúc gồm nhiều thành phần. Các hàm lồng nhau thể hiện quan hệ cha-con rõ ràng:

```kotlin
pipeline {
    stage("build") {
        step("compile")
        step("package")
    }
    stage("test") {
        step("unit-tests")
    }
}
```

Đây là cú pháp minh họa. `pipeline`, `stage` và `step` có thể tạo cây cấu hình cho một quy trình. Cấu trúc lồng nhau giúp người đọc nhìn thấy các giai đoạn và bước thuộc về nhau.

### 6.3. Lambda có receiver

Trong Kotlin, một kiểu hàm như `Order.() -> Boolean` mô tả lambda được thực thi trong ngữ cảnh của một `Order`. Bên trong lambda, có thể truy cập thuộc tính của đối tượng receiver mà không cần viết tên biến ở mỗi lần:

```kotlin
fun eligible(order: Order): Boolean = with(order) {
    total >= 1_000_000 && status == OrderStatus.PAID
}
```

Khi thư viện DSL định nghĩa hàm nhận lambda có receiver, nó có thể tạo cú pháp gọn như `whenOrder { total >= 1_000_000 }`. Cơ chế này giúp biểu thức gần với ngôn ngữ miền, nhưng người đọc cần hiểu receiver hiện tại là đối tượng nào.

### 6.4. Kiểu dữ liệu và kiểm tra tĩnh

Có thể tạo kiểu riêng để tránh nhầm lẫn giữa các giá trị cùng kiểu lưu trữ. Ví dụ, `CustomerId` và `OrderId` đều có thể được biểu diễn bằng chuỗi, nhưng không nên truyền nhầm cho nhau. Kiểu miền, generic, interface và overload có thể giúp trình biên dịch phát hiện một số lỗi trước khi chạy.

Không phải mọi điều kiện nghiệp vụ đều có thể kiểm tra tĩnh. Điều kiện phụ thuộc dữ liệu thực tế, quyền của người dùng hoặc trạng thái hệ thống thường cần xác thực lúc chạy.

### 6.5. Toán tử và cú pháp gần miền

Một số ngôn ngữ cho phép định nghĩa lại ý nghĩa của toán tử hoặc cung cấp cú pháp infix. Điều này có thể làm biểu thức tự nhiên hơn, ví dụ `price is greaterThan threshold` hoặc kết hợp điều kiện bằng toán tử logic.

Tuy nhiên, không nên lạm dụng operator overloading. Nếu toán tử `+` được dùng để cộng tiền, nối chuỗi và đồng thời thêm điều kiện vào một cây truy vấn, người đọc khó dự đoán ý nghĩa. Chỉ dùng cú pháp đặc biệt khi ý nghĩa nhất quán và quen thuộc.

## 7. Ưu điểm của DSL nội bộ

### 7.1. Tận dụng hệ sinh thái sẵn có

DSL nội bộ dùng lại trình biên dịch, parser, IDE, công cụ định dạng, kiểm thử và thư viện của ngôn ngữ chủ. Nhóm phát triển không nhất thiết phải xây dựng toàn bộ công cụ ngôn ngữ từ đầu.

### 7.2. Dễ tích hợp với chương trình hiện tại

Vì DSL được triển khai bằng cùng ngôn ngữ với ứng dụng, nó có thể truy cập trực tiếp kiểu dữ liệu, module, hàm và thư viện của chương trình. Không cần nhất thiết tạo một tiến trình parser riêng hoặc một định dạng trung gian qua ranh giới hệ thống.

### 7.3. Có thể tận dụng kiểm tra kiểu

Khi ngôn ngữ chủ có hệ thống kiểu tĩnh, một phần lỗi như gọi sai phương thức, truyền nhầm kiểu hoặc thiếu tham số có thể được phát hiện trong quá trình biên dịch. Điều này phụ thuộc vào cách DSL được thiết kế và không thay thế kiểm tra quy tắc nghiệp vụ lúc chạy.

### 7.4. Có thể dễ học với người đã biết ngôn ngữ chủ

Nhà phát triển quen Kotlin có thể học một DSL Kotlin nhanh hơn vì họ đã biết lambda, extension function và kiểu dữ liệu. Tương tự, người dùng Ruby có thể nhận ra block và lời gọi phương thức trong RSpec.

### 7.5. Dễ tái sử dụng và kiểm thử

DSL nội bộ thường được đóng gói thành thư viện, có thể chia module, viết unit test và dùng lại trong nhiều dự án. Nếu DSL tạo mô hình trung gian trước khi thực thi, có thể kiểm tra cấu trúc mô hình độc lập với hệ thống bên ngoài.

## 8. Hạn chế và chi phí của DSL nội bộ

### 8.1. Bị giới hạn bởi cú pháp ngôn ngữ chủ

Người thiết kế không thể tự do tạo một ngữ pháp hoàn toàn mới. Cú pháp có thể dài dòng hoặc chứa dấu ngoặc, dấu chấm và tên hàm mà chuyên gia miền không quen. Một biểu thức được mong muốn có thể không biểu đạt tự nhiên trong ngôn ngữ chủ.

### 8.2. Người dùng cần biết ngôn ngữ chủ

DSL nội bộ thường phù hợp nhất với lập trình viên hoặc người đã quen môi trường ngôn ngữ chủ. Chuyên gia nghiệp vụ không biết Kotlin, Ruby hoặc Java có thể khó đọc và sửa các biểu thức, dù tên hàm được đặt theo thuật ngữ miền.

### 8.3. Khó tách biệt cú pháp DSL với mã chương trình

Vì DSL là mã của ngôn ngữ chủ, một biểu thức có thể gọi những hàm hoặc thao tác ngoài phạm vi dự kiến nếu thư viện không kiểm soát chặt. Cũng có thể khó xác định một khối mã là cấu hình khai báo hay logic tùy ý.

### 8.4. Rủi ro tạo API quá phức tạp

Nếu DSL có quá nhiều overload, extension, generic, toán tử và kiểu builder, thông báo lỗi có thể khó hiểu. Người dùng phải biết chi tiết triển khai để hiểu vì sao một biểu thức không biên dịch.

### 8.5. Gắn chặt với nền tảng

Biểu thức DSL có thể phụ thuộc vào phiên bản ngôn ngữ chủ, thư viện hoặc framework. Nếu ứng dụng chuyển từ một ngôn ngữ sang ngôn ngữ khác, DSL và các biểu thức hiện có có thể phải viết lại.

### 8.6. Không tự động an toàn

DSL nội bộ chạy trong môi trường của ngôn ngữ chủ và có thể kế thừa quyền truy cập của chương trình. Nếu người dùng không đáng tin cậy có thể cung cấp mã DSL, cần cân nhắc sandbox, giới hạn API, kiểm soát quyền và tài nguyên. Việc gọi một API là DSL không tự tạo ra ranh giới bảo mật.

## 9. So sánh DSL nội bộ và DSL bên ngoài

| Tiêu chí | DSL nội bộ (embedded) | DSL bên ngoài (external) |
|---|---|---|
| Cú pháp | Dựa trên cú pháp của ngôn ngữ chủ | Có ngữ pháp riêng |
| Phân tích cú pháp | Dùng parser của ngôn ngữ chủ | Thường cần parser riêng hoặc công cụ sinh parser |
| Công cụ | Có thể dùng lại IDE, debugger và hệ thống kiểu của ngôn ngữ chủ | Cần công cụ chuyên biệt hoặc tích hợp thêm vào IDE |
| Người dùng | Thường là lập trình viên biết ngôn ngữ chủ | Có thể thiết kế cho chuyên gia miền không biết ngôn ngữ chủ |
| Tự do cú pháp | Bị giới hạn bởi ngôn ngữ chủ | Kiểm soát cú pháp độc lập hơn |
| Tích hợp | Trực tiếp với mã và kiểu của ứng dụng | Thường cần chuyển đổi qua AST, dữ liệu hoặc giao thức |
| Bảo trì | Phụ thuộc thư viện DSL và phiên bản ngôn ngữ chủ | Phụ thuộc parser, runtime và công cụ DSL |
| Ví dụ | RSpec, Gradle Kotlin DSL, DSL builder trong Kotlin | SQL, regex, ngôn ngữ cấu hình có grammar riêng |

Không có loại nào luôn tốt hơn. DSL nội bộ có lợi khi người dùng chủ yếu là lập trình viên, ngôn ngữ chủ phù hợp và việc tích hợp với ứng dụng là quan trọng. DSL bên ngoài phù hợp hơn khi cần cú pháp độc lập, cần giới hạn biểu đạt chặt chẽ hoặc muốn người dùng không cần biết ngôn ngữ lập trình chủ.

## 10. Khi nào nên chọn DSL nội bộ?

DSL nội bộ thường là lựa chọn hợp lý khi:

- Đội ngũ phát triển đã sử dụng một ngôn ngữ chủ ổn định.
- Người viết DSL chủ yếu là lập trình viên hoặc người có thể học ngôn ngữ chủ.
- Cần tích hợp chặt với kiểu dữ liệu, thư viện và module hiện có.
- Cú pháp của ngôn ngữ chủ đủ linh hoạt để diễn đạt khái niệm miền.
- Muốn tận dụng hệ thống kiểu, IDE, debugger và công cụ kiểm thử sẵn có.
- Phạm vi DSL tương đối nhỏ và có thể được cung cấp như một API thư viện.

DSL nội bộ có thể không phù hợp nếu chuyên gia nghiệp vụ cần tự viết quy tắc nhưng không biết ngôn ngữ chủ, nếu cú pháp chuyên biệt phải rất khác cú pháp ngôn ngữ chủ, hoặc nếu cần một định dạng độc lập có thể được trao đổi giữa nhiều nền tảng.

### Câu hỏi hỗ trợ quyết định

1. Ai sẽ đọc và viết các biểu thức: lập trình viên, chuyên gia nghiệp vụ hay cả hai?
2. Người dùng đã biết ngôn ngữ chủ đến mức nào?
3. Cú pháp chủ có thể biểu đạt rõ các khái niệm miền không?
4. DSL cần thực thi ngay hay cần lưu trữ và trao đổi như một tài liệu độc lập?
5. Cần kiểm soát chặt những thao tác nào mà biểu thức được phép thực hiện?
6. Mức độ phụ thuộc vào framework hoặc phiên bản ngôn ngữ chủ có chấp nhận được không?
7. Chi phí xây dựng parser riêng cho DSL bên ngoài có lớn hơn lợi ích của cú pháp độc lập không?

## 11. Nguyên tắc thiết kế DSL nội bộ dễ sử dụng

### 11.1. Bắt đầu từ ngôn ngữ của miền

Thu thập các khái niệm, hành động và quy tắc mà người trong miền thường dùng. Đặt tên API theo các khái niệm đó, nhưng giữ nghĩa nhất quán. Đừng bắt đầu bằng việc phô diễn các tính năng nâng cao của ngôn ngữ chủ.

### 11.2. Giữ cú pháp nhỏ và nhất quán

Chỉ cung cấp cấu trúc cần thiết cho những tình huống thường gặp. Nếu hai hàm có ý nghĩa gần nhau, cần nêu rõ khác biệt. Tránh nhiều cách viết khác nhau cho cùng một hành vi nếu không có lý do.

### 11.3. Dùng kiểu để loại bỏ trạng thái không hợp lệ

Có thể thiết kế builder theo từng giai đoạn để chỉ cho phép gọi thao tác hợp lệ. Ví dụ, builder truy vấn chỉ cho phép gọi `where` sau khi đã chọn nguồn dữ liệu. Kiểu dữ liệu có thể giúp giới hạn thứ tự thao tác và phát hiện lỗi sớm.

### 11.4. Làm rõ ngữ cảnh của lambda

Khi dùng lambda có receiver hoặc block lồng nhau, người viết phải biết biểu thức đang thao tác trên đối tượng nào. Tên tham số rõ ràng, kiểu cụ thể và cấu trúc lồng hợp lý giúp giảm nhầm lẫn.

### 11.5. Cung cấp thông báo lỗi theo ngôn ngữ miền

Thông báo kiểu “No applicable overload found” thường khó hiểu với người dùng DSL. Có thể bổ sung lỗi có ngữ cảnh như “Điều kiện `total` yêu cầu giá trị kiểu Money nhưng nhận được Percentage”. Tài liệu nên giải thích cấu trúc hợp lệ và đưa ví dụ.

### 11.6. Tách mô tả khỏi tác động khi cần

Nếu DSL mô tả quy trình quan trọng, hãy cân nhắc tạo mô hình trung gian trước khi thực thi. Điều này cho phép kiểm tra, xem trước, ghi log và phê duyệt biểu thức trước khi tạo tác động lên hệ thống.

### 11.7. Viết kiểm thử cho cả cú pháp và ngữ nghĩa

Kiểm thử cần bao gồm biểu thức hợp lệ, biểu thức không hợp lệ, kiểu sai, trường hợp biên và kết quả thực thi. Nếu DSL tạo AST hoặc cấu hình, có thể kiểm tra cấu trúc trung gian để phát hiện thay đổi ngoài ý muốn.

## 12. Một ví dụ thiết kế DSL nội bộ từ đầu

Giả sử ứng dụng cần mô tả điều kiện đủ tư cách nhận ưu đãi. Quy tắc nghiệp vụ là khách hàng phải đang hoạt động và tổng chi tiêu trong năm ít nhất 5.000.000 đồng.

### 12.1. Biểu diễn trực tiếp bằng ngôn ngữ chủ

```kotlin
fun isEligible(customer: Customer): Boolean {
    return customer.isActive && customer.yearlySpend >= 5_000_000
}
```

Cách viết này rõ với lập trình viên Kotlin, nhưng nếu có nhiều quy tắc tương tự, người đọc có thể muốn một cấu trúc biểu đạt thống nhất cho điều kiện và hành động.

### 12.2. Đề xuất cú pháp DSL

```kotlin
eligibilityRule("loyal-customer") {
    require { isActive }
    require { yearlySpend >= 5_000_000 }
}
```

Đây là cú pháp minh họa. DSL diễn đạt quy tắc bằng các khối `require`, còn tên `loyal-customer` xác định quy tắc. Nếu thư viện định nghĩa `require` nhận một lambda có receiver là `Customer`, mỗi điều kiện có thể truy cập thuộc tính khách hàng trực tiếp.

### 12.3. Cấu trúc mà thư viện có thể tạo

Thay vì thực thi ngay, thư viện có thể lưu hai điều kiện thành danh sách các biểu thức hoặc hàm kiểm tra:

```text
EligibilityRule
  name: "loyal-customer"
  conditions:
    - customer.isActive == true
    - customer.yearlySpend >= 5_000_000
```

Khi nhận một khách hàng, bộ đánh giá kiểm tra từng điều kiện và trả về kết quả. Một hệ thống hoàn chỉnh có thể trả thêm lý do không đủ điều kiện để giao diện giải thích cho người dùng.

### 12.4. Điều cần xác định trước khi triển khai

- `yearlySpend` tính theo năm dương lịch, năm tài chính hay 12 tháng gần nhất?
- Tổng chi tiêu có bao gồm đơn bị hủy hoặc hoàn tiền không?
- Đơn vị tiền tệ và cách xử lý giao dịch ngoại tệ là gì?
- Nếu dữ liệu chi tiêu chưa được đồng bộ thì điều kiện được coi là sai, chưa xác định hay cần chờ?
- Hai điều kiện được kết hợp theo AND hay có thể dùng OR?
- Ai có quyền thay đổi quy tắc và khi nào quy tắc mới có hiệu lực?

Những câu hỏi này cho thấy thiết kế cú pháp chỉ là một phần của DSL. Ngữ nghĩa miền phải được xác định trước để thư viện thực hiện đúng điều mà biểu thức mô tả.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu chính xác |
|---|---|
| DSL nội bộ là ngôn ngữ chỉ dùng trong công ty | “Nội bộ” nói về việc DSL được nhúng trong ngôn ngữ chủ |
| DSL nội bộ không phải ngôn ngữ thật | Nó là cách tổ chức cú pháp và API để biểu đạt một miền; vẫn dựa trên ngôn ngữ chủ |
| Mọi fluent API đều là DSL tốt | Fluent API chỉ là một kỹ thuật; DSL cần từ vựng và ngữ nghĩa miền rõ ràng |
| Có DSL nội bộ thì không cần hiểu ngôn ngữ chủ | Người viết vẫn phải tuân theo cú pháp và quy tắc của ngôn ngữ chủ |
| DSL nội bộ luôn dễ đọc hơn DSL bên ngoài | Mức độ dễ đọc phụ thuộc vào người dùng và cách thiết kế |
| Lambda lồng nhau tự động tạo ra DSL | Lambda chỉ là cơ chế; ý nghĩa miền phải được thư viện định nghĩa |
| DSL nội bộ tự động an toàn | Quyền và tác động phụ thuộc vào API được cung cấp và môi trường thực thi |

## 14. Kết luận

DSL nội bộ là ngôn ngữ chuyên biệt được xây dựng bằng cú pháp và cơ chế của một ngôn ngữ lập trình chủ. Nó thường được triển khai dưới dạng thư viện với các hàm, phương thức, builder, lambda, kiểu dữ liệu và fluent API mang ý nghĩa của miền.

Ưu điểm chính là tận dụng parser, hệ thống kiểu và công cụ phát triển có sẵn, đồng thời tích hợp trực tiếp với chương trình. Hạn chế chính là cú pháp bị ràng buộc bởi ngôn ngữ chủ và người viết thường cần hiểu ngôn ngữ đó. Khi chọn DSL nội bộ, hãy xem xét ai sẽ sử dụng, cú pháp chủ có diễn đạt tự nhiên được miền hay không, mức độ tích hợp cần thiết và cách kiểm soát hành vi thực thi.

Một DSL nội bộ tốt không chỉ làm mã trông khác đi. Nó tạo ra một cách diễn đạt nhất quán, có ý nghĩa rõ ràng và giúp người dùng mô tả công việc thuộc miền hiệu quả hơn.
