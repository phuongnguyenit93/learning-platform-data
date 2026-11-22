# Tùy chọn và giá trị mặc định trong cú pháp DSL

Một DSL cần quy định người dùng phải viết những thành phần nào và có thể bỏ qua những thành phần nào. Nếu mọi thông tin đều bắt buộc, mô tả có thể dài và lặp lại nhiều giá trị giống nhau. Nếu quá nhiều thành phần được phép bỏ qua mà không có quy tắc rõ ràng, người dùng khó dự đoán hệ thống sẽ hiểu mô tả như thế nào.

Hai cơ chế thường được dùng để cân bằng điều này là **tùy chọn** (*optional elements*) và **giá trị mặc định** (*default values*). Thành phần tùy chọn cho phép một phần cú pháp có thể xuất hiện hoặc không. Giá trị mặc định quy định hệ thống sử dụng giá trị nào khi người viết không cung cấp giá trị tương ứng.

Ví dụ, trong DSL mô tả tác vụ:

```text
task "build" {
    command = "gradle build"
}
```

người dùng có thể không khai báo thời gian chờ hoặc số lần thử lại. Ngôn ngữ có thể quy định timeout mặc định là 60 giây và số lần thử lại mặc định là 0. Nhờ đó, mô tả ngắn gọn vẫn có hành vi xác định.

## 1. Thành phần tùy chọn là gì?

**Optional element** là thành phần cú pháp không bắt buộc phải xuất hiện trong một cấu trúc. Nếu thành phần không xuất hiện, chương trình vẫn có thể hợp lệ theo grammar.

Ví dụ, một khai báo tác vụ có thể yêu cầu tên và lệnh, nhưng cho phép thêm timeout:

```text
task "build" {
    command = "gradle build"
    timeout = 120
}
```

Trong ví dụ này, timeout là thành phần tùy chọn nếu grammar cho phép bỏ dòng đó. Tên tác vụ và command vẫn là thành phần bắt buộc.

Một thành phần có thể tùy chọn ở nhiều cấp:

- **Tùy chọn toàn bộ mệnh đề:** người dùng có thể bỏ cả một dòng hoặc block, chẳng hạn retry.
- **Tùy chọn một thuộc tính:** block vẫn cần có, nhưng một thuộc tính bên trong có thể thiếu.
- **Tùy chọn đối số:** một hàm hoặc lệnh cho phép bỏ một tham số.
- **Tùy chọn phần tử lặp:** một danh sách có thể không có phần tử nào hoặc có nhiều phần tử.
- **Tùy chọn nhánh:** một cấu trúc có thể có nhánh else hoặc không.

Cần phân biệt thành phần tùy chọn với thành phần có giá trị rỗng. Nếu grammar cho phép bỏ timeout, điều đó không tự động có nghĩa là người dùng có thể viết null hoặc 0. Mỗi cách biểu diễn cần có ngữ nghĩa riêng.

## 2. Giá trị mặc định là gì?

**Default value** là giá trị mà DSL hoặc bộ xử lý sử dụng khi người dùng không cung cấp giá trị tường minh cho một tùy chọn.

Ví dụ, một tác vụ có thể có số lần thử lại mặc định là 0:

```text
task "compile" {
    command = "gradle compile"
}
```

Nếu người dùng không khai báo retries, runtime có thể coi giá trị đó là 0. Khi muốn thử lại hai lần, người dùng ghi:

```text
task "compile" {
    command = "gradle compile"
    retries = 2
}
```

Giá trị mặc định giúp mô tả ngắn hơn và tạo hành vi nhất quán. Tuy nhiên, default phải được tài liệu hóa rõ ràng. Người dùng cần biết:

- Giá trị nào được dùng nếu bỏ qua thuộc tính?
- Giá trị đó đến từ grammar, DSL, môi trường hay ứng dụng?
- Có thể ghi đè giá trị mặc định không?
- Giá trị mặc định được xác định tại thời điểm phân tích hay khi chạy?
- Khi giá trị mặc định không hợp lệ trong ngữ cảnh hiện tại thì hệ thống xử lý ra sao?

Giá trị mặc định là một phần của ngữ nghĩa DSL, không chỉ là tiện ích của giao diện nhập liệu.

## 3. Quan hệ giữa tùy chọn và giá trị mặc định

Hai khái niệm liên quan nhưng không đồng nghĩa.

- **Optional** trả lời: người dùng có bắt buộc phải viết thành phần này không?
- **Default** trả lời: nếu người dùng không viết, hệ thống sẽ dùng giá trị nào?

Một thuộc tính có thể tùy chọn và có default. Đây là trường hợp phổ biến: người dùng có thể bỏ qua, và hệ thống dùng giá trị mặc định.

Một thuộc tính có thể tùy chọn nhưng không có default. Khi bỏ qua, giá trị có thể vẫn chưa xác định; hệ thống có thể không thực hiện tính năng liên quan hoặc giữ trạng thái “không được cấu hình”.

Một thuộc tính có thể bắt buộc nhưng vẫn có giá trị được đề xuất trong editor. Gợi ý trong giao diện không biến nó thành tùy chọn; người dùng vẫn phải xác nhận hoặc cung cấp giá trị để chương trình hợp lệ.

| Thành phần | Có thể bỏ qua? | Có default? | Ý nghĩa khi bỏ qua |
|---|---:|---:|---|
| timeout | Có | Có, 60 giây | Dùng 60 giây |
| description | Có | Không | Không có mô tả |
| region | Không | Không | Báo lỗi thiếu giá trị |
| cache | Có | Có, true | Bật cache |
| fallback | Có | Không | Không khai báo nhánh dự phòng |

Các giá trị trong bảng chỉ là ví dụ. Mỗi DSL cần tự định nghĩa chính sách của mình.

## 4. Các hình thức cú pháp tùy chọn

### 4.1. Mệnh đề tùy chọn

Một cấu trúc có thể cho phép người dùng thêm một mệnh đề khi cần:

```text
query products {
    where price > 100
    order_by name
}
```

Trong ví dụ giả định này, where và order_by có thể là các mệnh đề tùy chọn. Nếu không có where, truy vấn có thể lấy toàn bộ sản phẩm; nếu không có order_by, thứ tự kết quả có thể không được đảm bảo.

### 4.2. Thuộc tính tùy chọn trong block

Một block có thể chứa các thuộc tính bắt buộc và tùy chọn:

```text
service "catalog" {
    image = "catalog:v2"
    replicas = 3
    memory = "512Mi"
}
```

Giả sử image là bắt buộc, còn replicas và memory có thể được bỏ qua. Nếu bỏ qua, hệ thống dùng giá trị mặc định được quy định cho từng thuộc tính.

### 4.3. Cờ bật/tắt (flag)

Một số DSL dùng cờ để biểu thị lựa chọn Boolean:

```text
build "release" {
    command = "gradle build"
    cache
    verbose
}
```

Ở dạng này, sự xuất hiện của cache có thể mang nghĩa bật cache; không xuất hiện có thể mang nghĩa tắt hoặc dùng default. Cần định nghĩa rõ liệu một flag mặc định là bật hay tắt, và có cú pháp tường minh để ghi đè hay không, chẳng hạn cache = false.

### 4.4. Đối số tùy chọn

Một lệnh hoặc hàm trong DSL có thể cho phép bỏ đối số cuối:

```text
notify("team@example.com")
notify("team@example.com", "Build completed")
```

Đối số thứ hai có thể là nội dung thông báo tùy chọn. Nếu bị bỏ, hệ thống có thể dùng nội dung mặc định. Với DSL có đối số theo vị trí, nên tránh quá nhiều tham số tùy chọn vì người viết khó nhớ vị trí và kiểu của từng giá trị.

### 4.5. Danh sách có thể rỗng

Một cấu trúc danh sách có thể cho phép không có phần tử nào:

```text
permissions = []
```

Danh sách rỗng khác với việc không khai báo permissions. Danh sách rỗng có thể mang nghĩa “không cấp quyền nào”; không khai báo có thể mang nghĩa “dùng quyền mặc định”. Sự khác biệt này rất quan trọng trong các DSL cấu hình bảo mật.

## 5. Phân biệt không khai báo, null, giá trị rỗng và giá trị mặc định

Đây là một trong những điểm quan trọng nhất khi thiết kế cú pháp tùy chọn. Các trường hợp sau có thể mang ý nghĩa khác nhau:

- **Không khai báo (absent):** thuộc tính không xuất hiện trong mô tả.
- **Null:** người viết chủ động khai báo rằng thuộc tính không có giá trị hoặc không áp dụng.
- **Giá trị rỗng (empty):** có giá trị nhưng không chứa nội dung, ví dụ chuỗi rỗng hoặc danh sách rỗng.
- **Giá trị mặc định (default):** giá trị do ngôn ngữ hoặc runtime cung cấp khi một điều kiện cụ thể xảy ra.
- **Giá trị mặc định của kiểu (zero value):** giá trị nền tảng gán cho kiểu dữ liệu, nếu có. Giá trị này không nhất thiết là default nghiệp vụ của DSL.

Ví dụ với thuộc tính description:

```text
task "build" {
    command = "gradle build"
}
```

```text
task "build" {
    command = "gradle build"
    description = null
}
```

```text
task "build" {
    command = "gradle build"
    description = ""
}
```

Một DSL có thể quy định ba trường hợp lần lượt có nghĩa:

| Trường hợp | Ý nghĩa minh họa |
|---|---|
| Không khai báo description | Dùng mô tả được kế thừa hoặc không có mô tả |
| description = null | Xóa hoặc vô hiệu hóa mô tả kế thừa |
| description = "" | Có mô tả tường minh nhưng nội dung là chuỗi rỗng |

Không có một quy tắc chung bắt buộc mọi DSL phải áp dụng. Điều quan trọng là định nghĩa rõ từng trường hợp và giữ cách xử lý nhất quán.

### Vì sao absent và null cần được phân biệt?

Giả sử cấu hình cha quy định timeout là 60 giây. Cấu hình con không khai báo timeout có thể kế thừa 60 giây. Nếu cấu hình con khai báo timeout là null, ngôn ngữ có thể hiểu là bỏ timeout hoặc yêu cầu hệ thống không kế thừa giá trị cha.

Nếu hệ thống gộp absent và null thành một trường hợp, người dùng có thể không có cách nào ghi đè hoặc xóa giá trị được kế thừa. Vì vậy, khi cần kế thừa cấu hình, cần xem xét biểu diễn trạng thái “không cung cấp” riêng với “cung cấp null”.

## 6. Các nguồn tạo ra giá trị mặc định

Giá trị mặc định có thể được xác định ở nhiều nơi. Cần chỉ rõ nguồn để người dùng biết giá trị đến từ đâu và thay đổi ở đâu.

### 6.1. Default được quy định trong đặc tả DSL

Đây là giá trị do ngôn ngữ quy định, áp dụng nhất quán cho mọi bộ xử lý tương thích.

Ví dụ, nếu thuộc tính retries không được khai báo, DSL quy định giá trị là 0. Một runtime tuân theo đặc tả cần áp dụng đúng giá trị này.

### 6.2. Default của ứng dụng hoặc runtime

Ứng dụng có thể cung cấp giá trị mặc định cho những thuộc tính mà DSL không quy định. Ví dụ, một engine có thể dùng timeout 30 giây nếu tệp DSL bỏ qua thuộc tính này.

Cách làm này linh hoạt theo môi trường, nhưng có thể khiến cùng một tệp DSL hoạt động khác nhau ở các môi trường. Nếu đây là chủ ý, cần tài liệu hóa và có cách quan sát giá trị hiệu lực.

### 6.3. Default được kế thừa

Một block con có thể nhận giá trị từ block cha hoặc cấu hình cấp cao hơn.

Ví dụ:

```text
environment "production" {
    timeout = 90

    task "publish" {
        command = "deploy"
    }
}
```

Nếu task publish không khai báo timeout, nó có thể kế thừa 90 giây từ environment. DSL cần quy định thuộc tính nào được kế thừa, phạm vi kế thừa và cách ghi đè.

### 6.4. Default theo ngữ cảnh

Giá trị có thể phụ thuộc vào miền hoặc ngữ cảnh thực thi. Ví dụ, số lần thử lại có thể là 3 cho thao tác đọc dữ liệu và 0 cho thao tác chuyển tiền.

Default theo ngữ cảnh có thể giúp cấu hình ngắn gọn, nhưng làm tăng độ phức tạp khi giải thích hành vi. Công cụ nên cho người dùng xem giá trị hiệu lực cùng nguồn đã tạo ra nó.

### 6.5. Default được tính toán

Một giá trị mặc định có thể được tính từ các thuộc tính khác:

```text
task "test" {
    workers = 4
    memory_per_worker = "256Mi"
    total_memory = auto
}
```

Trong ví dụ giả định, total_memory có thể được tính từ workers và memory_per_worker. DSL cần quy định công thức, thời điểm tính và hành vi nếu một đầu vào bị thiếu.

### 6.6. Default từ môi trường

Một số giá trị có thể lấy từ biến môi trường, cấu hình triển khai hoặc hệ thống. Cách này thường dùng cho endpoint, vùng triển khai hoặc thông tin không nên ghi cứng trong tệp.

Ví dụ, DSL có thể cho phép:

```text
service "catalog" {
    endpoint = env("CATALOG_ENDPOINT")
}
```

Giá trị phụ thuộc môi trường cần được xác thực khi nạp hoặc khi chạy. Không nên giả định biến môi trường luôn tồn tại hoặc luôn có kiểu đúng.

## 7. Thứ tự ưu tiên khi có nhiều nguồn giá trị

Khi một thuộc tính có thể nhận giá trị từ nhiều nguồn, DSL cần quy định **precedence** – thứ tự ưu tiên. Nếu không, người dùng khó biết giá trị nào cuối cùng được sử dụng.

Một chính sách minh họa có thể là:

1. Giá trị được khai báo trực tiếp tại thuộc tính.
2. Giá trị từ block gần nhất bao quanh thuộc tính.
3. Giá trị từ cấu hình kế thừa hoặc profile.
4. Giá trị mặc định do DSL quy định.
5. Giá trị dự phòng của runtime.

Thứ tự này chỉ là ví dụ. Một DSL có thể dùng quy tắc khác, chẳng hạn giá trị command line ưu tiên hơn tệp cấu hình, hoặc giá trị policy cấp tổ chức không thể bị ghi đè bởi cấu hình cục bộ.

Ví dụ:

```text
defaults {
    timeout = 60
}

environment "production" {
    timeout = 90

    task "publish" {
        timeout = 120
        command = "deploy"
    }

    task "cleanup" {
        command = "cleanup"
    }
}
```

Nếu quy tắc là ưu tiên khai báo gần nhất, task publish dùng 120 giây; task cleanup kế thừa 90 giây từ environment. Nếu environment không khai báo timeout, hai task có thể kế thừa 60 giây từ defaults.

### Bảng truy vết giá trị hiệu lực

Công cụ tốt nên giúp người dùng biết giá trị cuối cùng và nguồn của nó:

| Thuộc tính | Giá trị hiệu lực | Nguồn |
|---|---:|---|
| publish.timeout | 120 | Khai báo trực tiếp |
| cleanup.timeout | 90 | Block environment |
| audit.timeout | 60 | Block defaults |
| report.timeout | 30 | Runtime fallback |

Bảng chỉ là minh họa. Việc truy vết nguồn giúp giải thích cấu hình và tìm nguyên nhân khi một giá trị không như mong đợi.

## 8. Thời điểm áp dụng default

Default có thể được xác định ở các giai đoạn khác nhau.

### 8.1. Khi phân tích cú pháp hoặc tạo mô hình

Parser hoặc bước xây dựng AST có thể điền default ngay khi tạo node. Cách này tạo mô hình đầy đủ sớm, nhưng có thể làm mất thông tin liệu người dùng có khai báo tường minh hay không.

Nếu cần phân biệt giá trị tường minh với giá trị được suy ra, mô hình nên lưu cả giá trị và nguồn của giá trị.

### 8.2. Khi kiểm tra ngữ nghĩa hoặc chuẩn hóa

Semantic analyzer có thể xác định default sau khi biết kiểu và ngữ cảnh. Ví dụ, thuộc tính timeout của một loại task có thể có default khác loại task khác.

Giai đoạn này phù hợp khi default phụ thuộc domain model, loại node hoặc cấu hình cha.

### 8.3. Khi thực thi

Runtime có thể áp dụng default tại thời điểm chạy nếu giá trị phụ thuộc môi trường hoặc dữ liệu hiện thời.

Ví dụ, endpoint có thể được lấy từ môi trường triển khai. Cách này linh hoạt, nhưng kết quả có thể khác nhau giữa các lần chạy. Cần ghi nhận giá trị thực tế đã dùng nếu yêu cầu khả năng tái lập.

### Eager và lazy default

- **Eager default:** được tính hoặc gán ngay khi tạo mô hình.
- **Lazy default:** chỉ được tính khi thuộc tính thực sự được truy cập hoặc cần sử dụng.

Lazy default hữu ích khi phép tính tốn tài nguyên hoặc phụ thuộc dữ liệu chưa có ở thời điểm phân tích. Tuy nhiên, lỗi có thể xuất hiện muộn hơn. Đặc tả DSL cần nêu rõ thời điểm đánh giá để người dùng dự đoán được hành vi.


## 9. Kiểu dữ liệu của thuộc tính tùy chọn

Một thuộc tính tùy chọn vẫn cần có kiểu dữ liệu xác định. Kiểu dữ liệu giúp parser, validator và runtime hiểu giá trị nào được chấp nhận.

Ví dụ:

| Thuộc tính | Kiểu | Default minh họa | Ràng buộc |
|---|---|---|---|
| timeout | Duration | 60 giây | Lớn hơn 0 |
| retries | Integer | 0 | Từ 0 đến 5 |
| cache | Boolean | true | true hoặc false |
| description | String? | Không có | Có thể vắng mặt |
| tags | List<String> | Danh sách rỗng | Mỗi tag không rỗng |

Dấu hỏi trong kiểu String? thường biểu thị kiểu có thể chứa null trong một số hệ thống kiểu. Nó không tự động có nghĩa thuộc tính có thể vắng mặt trong cú pháp. DSL phải phân biệt:

- Thuộc tính có thể không được khai báo.
- Thuộc tính có thể được khai báo với giá trị null.
- Thuộc tính có kiểu nullable.
- Thuộc tính có default.

Đây là bốn quyết định có liên quan nhưng khác nhau.

### Giá trị default phải phù hợp với kiểu

Nếu retries có kiểu Integer, default phải là một số nguyên hợp lệ. Nếu timeout có kiểu Duration, giá trị mặc định cần có đơn vị rõ ràng. Tránh dùng số trần nếu người dùng có thể hiểu nhầm đó là mili giây, giây hay phút.

Ví dụ:

```text
timeout = 30s
retries = 2
cache = true
description = "Build the release artifact"
```

Nếu DSL cho phép biểu thức tính toán, kiểu của biểu thức cũng cần tương thích với kiểu thuộc tính.

## 10. Xác thực default và ràng buộc giá trị

Default không nên được xem là hợp lệ chỉ vì nó được hệ thống tự sinh ra. Nó cần tuân thủ cùng những ràng buộc áp dụng cho giá trị người dùng cung cấp.

Ví dụ, nếu retries phải nằm trong khoảng 0 đến 5, default 10 vẫn là lỗi thiết kế DSL hoặc lỗi cấu hình runtime.

Các dạng validation thường gặp:

- **Type validation:** giá trị có đúng kiểu không?
- **Range validation:** số có nằm trong khoảng cho phép không?
- **Format validation:** chuỗi có đúng định dạng không?
- **Domain validation:** giá trị có hợp lệ theo nghiệp vụ không?
- **Cross-field validation:** các thuộc tính có tương thích với nhau không?
- **Context validation:** giá trị có hợp lệ trong môi trường hoặc block hiện tại không?

Ví dụ, nếu cache được bật thì cache_directory có thể cần được cung cấp hoặc có default hợp lệ. Nếu retry được bật cho thao tác thanh toán, action có thể cần idempotency key. Những ràng buộc liên thuộc tính như vậy cần được kiểm tra sau khi giá trị hiệu lực đã được xác định.

### Hai thuộc tính loại trừ lẫn nhau

Một DSL có thể cho phép một trong hai lựa chọn:

```text
connection {
    url = "https://service.example"
    # Hoặc khai báo host và port theo dạng riêng
}
```

Nếu người dùng khai báo đồng thời hai dạng kết nối mà grammar hoặc semantics không cho phép, validator cần báo lỗi rõ ràng. Tùy chọn không có nghĩa là mọi tổ hợp của các tùy chọn đều hợp lệ.

### Default và bảo mật

Một số thuộc tính có ảnh hưởng đến quyền truy cập hoặc mức độ bảo vệ. Default của chúng cần được chọn cẩn thận.

Ví dụ, với DSL mô tả quyền, default rỗng có thể an toàn hơn việc tự cấp quyền rộng. Với DSL triển khai dịch vụ, default công khai một cổng mạng có thể gây rủi ro. Giá trị mặc định nên phản ánh nguyên tắc an toàn và kỳ vọng nghiệp vụ, đồng thời được giải thích trong tài liệu.

## 11. Cách biểu diễn tùy chọn trong grammar

Grammar cần mô tả rõ phần nào bắt buộc và phần nào có thể vắng mặt. Trong EBNF, dấu ngoặc vuông thường được dùng để biểu thị thành phần tùy chọn; dấu ngoặc nhọn thường biểu thị lặp không giới hạn hoặc lặp nhiều lần theo quy ước của EBNF.

Ví dụ, một khai báo task giả định:

```ebnf
task        = "task", string, "{", command, [timeout], [retry], "}" ;
command     = "command", "=", string ;
timeout     = "timeout", "=", duration ;
retry       = "retry", "=", integer ;
duration    = integer, ("ms" | "s" | "m") ;
```

Trong grammar trên:

- task, tên task và command là bắt buộc.
- timeout là tùy chọn.
- retry là tùy chọn.
- Grammar cho phép một timeout và một retry trong mỗi task.

Grammar không nhất thiết quy định đầy đủ giá trị default. Default thường thuộc semantic rules hoặc đặc tả thuộc tính. Ví dụ, nếu timeout bị bỏ qua, semantic analysis có thể điền 60 giây.

### Tùy chọn và thứ tự thành phần

Nếu grammar cho phép nhiều thuộc tính tùy chọn, cần quy định chúng có thể xuất hiện theo thứ tự bất kỳ hay phải theo thứ tự cố định.

Ví dụ, hai khai báo sau có thể được xem là tương đương nếu DSL cho phép thuộc tính theo thứ tự bất kỳ:

```text
task "build" {
    command = "gradle build"
    timeout = 90s
    retry = 2
}
```

```text
task "build" {
    retry = 2
    command = "gradle build"
    timeout = 90s
}
```

Nếu grammar yêu cầu thứ tự cố định, ví dụ thứ hai có thể không hợp lệ. Cần cân nhắc tính dễ đọc, khả năng mở rộng và sự nhất quán khi chọn quy tắc.

### Tùy chọn lặp và phần tử trùng

Một thuộc tính có thể xuất hiện nhiều lần nếu grammar cho phép. Tuy nhiên, DSL cần xác định hành vi khi trùng khóa:

- Báo lỗi nếu khai báo lặp.
- Lấy giá trị xuất hiện cuối cùng.
- Gộp các giá trị thành danh sách.
- Áp dụng quy tắc hợp nhất được định nghĩa riêng.

Không nên để hành vi phụ thuộc ngẫu nhiên vào thứ tự xử lý nội bộ.

## 12. Ví dụ tổng hợp: DSL cấu hình tác vụ

Giả sử ta thiết kế DSL để mô tả tác vụ build. Một số thuộc tính bắt buộc, một số có default và một số không có default.

### Đặc tả thuộc tính

| Thuộc tính | Bắt buộc? | Default | Ý nghĩa |
|---|---:|---|---|
| command | Có | Không | Lệnh thực thi |
| timeout | Không | 60s | Thời gian tối đa |
| retries | Không | 0 | Số lần thử lại |
| cache | Không | true | Có dùng cache hay không |
| description | Không | Không có | Mô tả hiển thị |
| tags | Không | [] | Nhãn để phân loại |

### Mô tả ngắn

```text
task "build" {
    command = "gradle build"
}
```

Giá trị hiệu lực:

- command = gradle build (do người dùng khai báo).
- timeout = 60s (default của DSL).
- retries = 0 (default của DSL).
- cache = true (default của DSL).
- description = absent (không có giá trị).
- tags = [] (default là danh sách rỗng).

### Mô tả ghi đè một số default

```text
task "release" {
    command = "gradle publish"
    timeout = 5m
    retries = 3
    cache = false
    description = "Publish the release"
    tags = ["release", "production"]
}
```

Trong trường hợp này, các giá trị do người dùng cung cấp ghi đè default tương ứng. Các thuộc tính không được khai báo vẫn dùng default hoặc trạng thái vắng mặt theo đặc tả.

### Mô hình hóa giá trị hiệu lực

Một biểu diễn nội bộ có thể lưu cả giá trị và nguồn:

```json
{
  "name": "build",
  "command": {
    "value": "gradle build",
    "source": "explicit"
  },
  "timeout": {
    "value": "60s",
    "source": "dsl-default"
  },
  "retries": {
    "value": 0,
    "source": "dsl-default"
  },
  "cache": {
    "value": true,
    "source": "dsl-default"
  },
  "description": {
    "value": null,
    "source": "absent"
  },
  "tags": {
    "value": [],
    "source": "dsl-default"
  }
}
```

JSON trên chỉ minh họa mô hình kết quả sau khi áp dụng default. Trong một triển khai thực tế, cấu trúc lưu nguồn giá trị có thể khác, nhưng việc giữ lại nguồn giúp giải thích tại sao một giá trị được sử dụng.


## 13. Tùy chọn trong nhiều lớp cấu hình

Một hệ thống có thể nhận giá trị từ nhiều lớp: mặc định của DSL, cấu hình tổ chức, cấu hình môi trường, block cha, block con và khai báo trực tiếp. Khi đó, default không chỉ là một con số hoặc chuỗi; nó tham gia vào một quy tắc hợp nhất cấu hình.

Ví dụ, một hệ thống build có thể có:

- Default chung: timeout 60 giây.
- Profile CI: timeout 120 giây.
- Cấu hình project: timeout 180 giây.
- Task cụ thể: timeout 30 giây.

Nếu quy tắc ưu tiên là cấu hình càng cụ thể càng cao, task cụ thể sẽ dùng 30 giây. Nhưng một số thuộc tính có thể có chính sách khác: giá trị cấp tổ chức có thể bị khóa và không cho project ghi đè.

Vì vậy, cần định nghĩa:

1. Các nguồn cấu hình được hỗ trợ.
2. Thứ tự ưu tiên giữa các nguồn.
3. Thuộc tính nào được phép kế thừa.
4. Thuộc tính nào được phép ghi đè.
5. Cách xử lý khi một nguồn cung cấp null hoặc danh sách rỗng.
6. Cách hiển thị giá trị hiệu lực và nguồn của nó.

### Hợp nhất danh sách và map

Không phải mọi kiểu dữ liệu đều nên dùng cùng một quy tắc hợp nhất.

- Với số hoặc chuỗi, giá trị từ nguồn ưu tiên cao có thể thay thế hoàn toàn giá trị cũ.
- Với danh sách, hệ thống có thể thay thế toàn bộ, nối thêm phần tử hoặc loại bỏ phần tử được kế thừa.
- Với map, hệ thống có thể gộp theo từng khóa hoặc thay thế toàn bộ map.
- Với Boolean, cần phân biệt false tường minh với không khai báo.

Ví dụ, cấu hình cha có tags là [ci, linux], cấu hình con khai báo tags là [release]. Nếu quy tắc là thay thế, kết quả là [release]. Nếu quy tắc là nối thêm, kết quả là [ci, linux, release]. DSL cần công bố cách xử lý này thay vì để người dùng suy đoán.

## 14. Thay đổi default và khả năng tương thích

Giá trị mặc định là một phần của hành vi ngôn ngữ. Thay đổi default có thể làm thay đổi kết quả của những tệp DSL không khai báo thuộc tính đó, dù văn bản nguồn không đổi.

Ví dụ, phiên bản đầu quy định cache mặc định là true. Phiên bản sau đổi thành false. Một task không khai báo cache sẽ có hành vi khác sau khi nâng cấp runtime.

Một số nguyên tắc quản lý:

- Ghi nhận default theo phiên bản DSL hoặc phiên bản runtime.
- Xem việc thay đổi default là thay đổi hành vi cần được thông báo.
- Có ghi chú migration khi default mới làm thay đổi kết quả.
- Cho phép người dùng khai báo tường minh giá trị nếu cần giữ hành vi cũ.
- Khi chạy lại một workflow hoặc build cũ, lưu lại phiên bản định nghĩa và chính sách default đã áp dụng.

### Default tĩnh và khả năng tái lập

Nếu default phụ thuộc môi trường, cùng một tệp có thể tạo kết quả khác nhau giữa máy phát triển và môi trường production. Để tái lập, hệ thống có thể lưu cấu hình đã chuẩn hóa (*resolved configuration*) hoặc snapshot các giá trị hiệu lực tại thời điểm chạy.

Với các tác vụ cần kiểm toán, nên ghi nhận:

- Phiên bản DSL.
- Phiên bản runtime.
- Các giá trị tường minh.
- Các giá trị được kế thừa hoặc lấy từ môi trường.
- Default đã được áp dụng.
- Thời điểm và ngữ cảnh thực thi.

Điều này giúp giải thích vì sao cùng một nguồn DSL có thể tạo ra kết quả khác nhau.

## 15. Tài liệu hóa tùy chọn và default

Mỗi thuộc tính tùy chọn nên có tài liệu đủ để người dùng hiểu hành vi. Tối thiểu, mô tả thuộc tính cần nêu:

| Nội dung | Điều cần giải thích |
|---|---|
| Tên | Tên thuộc tính và từ khóa tương ứng |
| Kiểu | Kiểu dữ liệu và đơn vị |
| Bắt buộc | Có thể bỏ qua hay phải khai báo |
| Default | Giá trị dùng khi không khai báo |
| Nguồn default | DSL, runtime, môi trường hay cấu hình kế thừa |
| Ràng buộc | Khoảng giá trị, định dạng và điều kiện liên thuộc tính |
| Precedence | Nguồn nào ghi đè nguồn nào |
| Null và empty | Ý nghĩa của null, chuỗi rỗng và danh sách rỗng |
| Ví dụ | Cách dùng mặc định và cách ghi đè |

Một tài liệu tốt nên có ví dụ cho cả trường hợp bỏ qua thuộc tính và trường hợp ghi giá trị tường minh. Nếu default thay đổi theo ngữ cảnh, tài liệu cần nêu rõ ngữ cảnh nào làm thay đổi nó.

## 16. Kiểm thử hành vi của tùy chọn và default

Kiểm thử cần xác nhận cả cách parser nhận cú pháp và cách runtime giải quyết giá trị.

Các nhóm trường hợp hữu ích:

1. **Bỏ qua thuộc tính:** xác nhận default được áp dụng đúng.
2. **Ghi giá trị tường minh:** xác nhận giá trị người dùng ghi đè default.
3. **Ghi giá trị bằng không hoặc false:** bảo đảm giá trị hợp lệ không bị xem nhầm là vắng mặt.
4. **Khai báo null:** xác nhận semantics của null đúng đặc tả.
5. **Chuỗi rỗng và danh sách rỗng:** xác nhận khác biệt với absent.
6. **Giá trị sai kiểu:** parser hoặc validator báo lỗi đúng giai đoạn.
7. **Giá trị ngoài phạm vi:** phát hiện vi phạm ràng buộc.
8. **Giá trị kế thừa:** kiểm tra thứ tự ưu tiên giữa block cha và con.
9. **Nhiều nguồn cấu hình:** kiểm tra precedence và quy tắc hợp nhất.
10. **Thay đổi phiên bản:** xác nhận hành vi khi default thay đổi.

Đối với default được tính toán hoặc lấy từ môi trường, cần kiểm thử khi đầu vào tồn tại, thiếu, sai kiểu hoặc thay đổi. Đối với default lazy, cần kiểm tra thời điểm lỗi xuất hiện và đảm bảo kết quả không thay đổi ngoài dự kiến.

## 17. Những lỗi thiết kế thường gặp

**Không phân biệt absent và null.** Khi hai trường hợp bị gộp, người dùng có thể không xóa được giá trị kế thừa hoặc không thể yêu cầu dùng default một cách tường minh.

**Dùng giá trị zero làm dấu hiệu vắng mặt.** Số 0, Boolean false, chuỗi rỗng và danh sách rỗng đều có thể là giá trị hợp lệ. Không nên dùng chúng để biểu thị “chưa cung cấp” nếu ngôn ngữ không quy định rõ.

**Có default nhưng không tài liệu hóa.** Người dùng phải đoán hành vi khi bỏ qua thuộc tính, dẫn đến cấu hình khó hiểu và kết quả bất ngờ.

**Default không qua validation.** Một giá trị do runtime tự gán vẫn có thể vi phạm kiểu hoặc ràng buộc miền. Default cần được kiểm tra như giá trị bình thường.

**Thứ tự ưu tiên không rõ.** Nếu nhiều nguồn có thể cung cấp một thuộc tính, phải có quy tắc precedence nhất quán và công cụ hiển thị nguồn của giá trị.

**Thay đổi default mà không quản lý phiên bản.** Một thay đổi nhỏ trong đặc tả có thể làm thay đổi hành vi của hàng loạt tệp DSL cũ. Cần đánh giá và thông báo ảnh hưởng.

**Có quá nhiều tùy chọn.** Một cấu trúc với hàng chục thuộc tính tùy chọn có thể khó hiểu và khó kiểm tra. Chỉ nên đưa vào DSL những lựa chọn có ý nghĩa trong miền; nhóm các thuộc tính liên quan khi cần.

**Tạo default phụ thuộc ngầm vào môi trường.** Nếu người dùng không biết một biến môi trường hoặc cấu hình bên ngoài ảnh hưởng đến kết quả, việc tái lập và gỡ lỗi sẽ khó khăn. Cần ghi rõ nguồn và giá trị hiệu lực.

## 18. Quy trình phân tích tùy chọn và default trong một DSL

Khi đọc hoặc thiết kế một DSL, có thể thực hiện theo trình tự sau:

1. Liệt kê các thành phần bắt buộc và tùy chọn trong từng cấu trúc.
2. Xác định kiểu dữ liệu và ràng buộc cho mỗi thuộc tính.
3. Ghi rõ giá trị default hoặc trạng thái khi không khai báo.
4. Phân biệt absent, null, empty, false và zero.
5. Xác định nguồn default: đặc tả, runtime, block cha, profile hay môi trường.
6. Quy định thứ tự ưu tiên và cách hợp nhất giữa các nguồn.
7. Xác định thời điểm áp dụng default: parsing, semantic analysis hay runtime.
8. Kiểm tra default có thỏa kiểu và ràng buộc miền không.
9. Tài liệu hóa giá trị hiệu lực và nguồn tạo ra nó.
10. Kiểm thử trường hợp bỏ qua, ghi đè, null, giá trị rỗng và thay đổi phiên bản.

Trình tự này giúp người thiết kế kiểm soát cả cú pháp lẫn hành vi. Một thuộc tính tùy chọn chỉ thực sự dễ dùng khi người dùng biết rõ điều gì xảy ra trong mọi trường hợp họ có thể viết hoặc bỏ qua.

## 19. Câu hỏi tự kiểm tra

1. Thành phần tùy chọn trong grammar là gì?
2. Giá trị mặc định có vai trò gì khi người dùng bỏ qua một thuộc tính?
3. Optional và default khác nhau như thế nào?
4. Vì sao absent, null, empty, false và zero cần được phân biệt?
5. Nêu các nguồn có thể cung cấp giá trị mặc định.
6. Precedence có ý nghĩa gì khi giá trị đến từ nhiều lớp cấu hình?
7. Default eager khác default lazy ở thời điểm đánh giá như thế nào?
8. Vì sao default cần được kiểm tra kiểu và ràng buộc?
9. Grammar có thể biểu diễn thành phần tùy chọn bằng ký pháp nào trong EBNF?
10. Tại sao thay đổi default có thể phá vỡ khả năng tương thích dù tệp DSL không thay đổi?
11. Hãy xác định thuộc tính bắt buộc, tùy chọn và default cho một DSL cấu hình dịch vụ.
12. Hãy giải thích cách hệ thống nên xử lý khi một thuộc tính được kế thừa từ block cha nhưng block con khai báo null.

Khi nắm được các khái niệm này, người học có thể đọc grammar để xác định phần nào được phép bỏ qua, giải thích giá trị hiệu lực được hình thành từ đâu và thiết kế quy tắc default nhất quán cho một DSL.
