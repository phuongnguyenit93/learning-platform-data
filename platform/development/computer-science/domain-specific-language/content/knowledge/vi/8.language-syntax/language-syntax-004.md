# Cú pháp dễ đọc

Trong một **Domain-Specific Language (DSL)**, cú pháp là cách người dùng biểu đạt các khái niệm và quy tắc của miền bằng một hình thức mà công cụ có thể phân tích. Một cú pháp dễ đọc giúp người viết diễn đạt đúng ý định, người review hiểu được hành vi và người bảo trì nhận ra tác động của thay đổi. Nó cũng giúp phát hiện lỗi sớm vì cấu trúc và quan hệ trong chương trình được thể hiện rõ ràng.

Dễ đọc không có nghĩa là biến DSL thành ngôn ngữ tự nhiên hoặc làm cho mọi khai báo ngắn nhất có thể. Một cú pháp tốt cần cân bằng giữa sự quen thuộc, tính nhất quán, độ rõ nghĩa, khả năng kiểm tra và chi phí học. Nếu cú pháp quá ngắn, người đọc phải đoán ý nghĩa. Nếu cú pháp quá dài và nhiều từ khóa, việc viết và rà soát trở nên nặng nề. Mục tiêu là để cấu trúc của chương trình phản ánh đúng cấu trúc của miền nghiệp vụ.

## 1. Cú pháp dễ đọc có ý nghĩa gì?

Một DSL dễ đọc thường có các đặc điểm:

- **Từ vựng gần với miền**: tên từ khóa, thao tác và thuộc tính dùng thuật ngữ mà người dùng mục tiêu hiểu.
- **Cấu trúc nhất quán**: các khai báo cùng loại có hình thức tương tự, quy tắc đặt tên và sắp xếp không thay đổi tùy tiện.
- **Quan hệ được thể hiện rõ**: người đọc nhận ra thành phần nào thuộc thành phần nào, điều kiện nào áp dụng cho hành động nào và thứ tự nào có ý nghĩa.
- **Ít mơ hồ**: một biểu thức hoặc khai báo có cách hiểu ổn định; trường hợp có thể hiểu theo nhiều cách được quy định rõ.
- **Dễ quét bằng mắt**: khoảng trắng, xuống dòng, nhóm và chú thích giúp nhận ra phần quan trọng.
- **Có thể phát hiện lỗi**: cấu trúc hỗ trợ parser và bộ kiểm tra đưa ra thông báo cụ thể khi chương trình không hợp lệ.

Khả năng đọc còn phụ thuộc người đọc. Một cú pháp tự nhiên với chuyên gia nghiệp vụ có thể xa lạ với lập trình viên; một cú pháp giống Java có thể quen thuộc với kỹ sư phần mềm nhưng khó dùng với người không lập trình. Vì vậy, trước khi thiết kế cú pháp, cần xác định ai sẽ viết, đọc, review và bảo trì chương trình DSL.

## 2. Bắt đầu từ ngôn ngữ của miền nghiệp vụ

Từ vựng của DSL nên xuất phát từ cách người trong miền gọi tên sự vật, trạng thái và thao tác. Nếu một hệ thống quản lý triển khai dùng các khái niệm `service`, `replica`, `health check` và `environment`, các tên này thường dễ hiểu hơn những tên kỹ thuật chung chung như `nodeA`, `item2` hoặc `operationX`.

Ví dụ, một DSL mô tả dịch vụ có thể dùng:

```text
service "orders-api" {
    image = "example/orders:2.4"
    replicas = 3

    expose port 8080
}
```

Người đọc có thể nhận ra đây là một dịch vụ, image được triển khai, số bản sao và cổng được mở. Các từ khóa có ý nghĩa theo miền và không đòi hỏi người đọc phải biết tên lớp hay cấu trúc nội bộ của chương trình xử lý DSL.

### 2.1. Dùng thuật ngữ ổn định

Một khái niệm nên có một tên thống nhất trong toàn bộ DSL. Nếu cùng một khái niệm lúc được gọi là `service`, lúc là `application`, lúc là `workload` mà không có khác biệt ngữ nghĩa, người dùng sẽ phải học nhiều từ cho cùng một việc.

Trước khi chốt từ khóa, nên lập bảng thuật ngữ gồm tên khái niệm, định nghĩa, từ đồng nghĩa đang được dùng trong nghiệp vụ và tên được chọn trong DSL. Nếu một thuật ngữ có nhiều nghĩa theo ngữ cảnh, cần chọn tên cụ thể hơn hoặc xác định rõ phạm vi.

| Khái niệm miền | Tên nên dùng nhất quán | Tránh dùng lẫn lộn khi cùng nghĩa |
|---|---|---|
| Dịch vụ được triển khai | `service` | `app`, `unit`, `component` |
| Số bản sao | `replicas` | `count`, `instances`, `copies` |
| Cổng được mở | `port` | `endpoint`, `socket` nếu không cùng nghĩa |
| Môi trường triển khai | `environment` | `stage`, `target`, `profile` nếu không phân biệt rõ |

### 2.2. Chọn tên thể hiện đúng vai trò

Tên định danh nên cho biết nó đại diện cho gì. Một tên như `maxRetries` cho thấy đây là số lần thử lại tối đa; tên `n` không cho biết vai trò nếu không có ngữ cảnh rõ. Tên hành động nên dùng động từ hoặc cụm động từ; tên sự kiện nên diễn tả điều đã xảy ra; tên trạng thái nên là một danh từ hoặc tính từ ổn định.

Ví dụ:

```text
action restartService(serviceName)
event ServiceRestarted(serviceName, occurredAt)
state Running
```

Quy ước này giúp người đọc phân biệt yêu cầu, kết quả và trạng thái mà không cần suy luận từ vị trí của chúng.

## 3. Làm rõ cấu trúc bằng nhóm và phạm vi

Một chương trình DSL thường chứa nhiều khai báo lồng nhau. Cú pháp cần thể hiện rõ ranh giới của từng nhóm và phạm vi mà một thuộc tính hoặc quy tắc áp dụng.

Ví dụ:

```text
service "orders-api" {
    image = "example/orders:2.4"
    replicas = 3

    resources {
        cpu = "500m"
        memory = "512Mi"
    }

    health_check {
        path = "/health"
        interval = 10s
        timeout = 2s
    }
}
```

Các khối `resources` và `health_check` nằm bên trong `service`, nên người đọc hiểu chúng là cấu hình của dịch vụ này. Dấu ngoặc nhọn đánh dấu phạm vi bắt đầu và kết thúc. Việc thụt lề làm quan hệ lồng nhau dễ nhận biết hơn, dù trong ví dụ này dấu ngoặc mới là yếu tố xác định cấu trúc cú pháp.

### 3.1. Chọn quy tắc lồng nhau rõ ràng

Nếu DSL cho phép một khối chứa các khối con, cần xác định rõ loại khai báo nào được phép xuất hiện bên trong. Ví dụ, `resources` có thể chỉ chứa `cpu` và `memory`; `health_check` có thể chứa `path`, `interval` và `timeout`. Một khối không nên chấp nhận mọi loại khai báo nếu chúng không có ý nghĩa trong ngữ cảnh đó.

Phạm vi rõ giúp công cụ phát hiện trường hợp đặt nhầm thuộc tính. Chẳng hạn, nếu `replicas` chỉ hợp lệ ở cấp `service`, parser hoặc semantic validator có thể báo lỗi khi thuộc tính này xuất hiện trong `health_check`.

### 3.2. Nhóm những thuộc tính có quan hệ

Các thuộc tính nên được nhóm theo ý nghĩa, không chỉ theo thứ tự chúng được thêm vào chương trình. Ví dụ, cấu hình tài nguyên, kiểm tra sức khỏe và biến môi trường là những nhóm khác nhau. Khi số lượng thuộc tính tăng, nhóm rõ ràng giúp người đọc tìm được phần cần sửa mà không phải quét toàn bộ file.

Không nên tạo quá nhiều cấp lồng nhau cho những nhóm chỉ có một thuộc tính. Cấu trúc quá sâu làm tăng dấu ngoặc và khiến người đọc phải di chuyển mắt nhiều hơn. Chỉ tạo khối con khi nó đại diện cho một nhóm khái niệm hoặc phạm vi có ý nghĩa.

## 4. Thiết kế biểu thức và toán tử dễ hiểu

DSL có thể hỗ trợ biểu thức số học, so sánh, logic hoặc điều kiện. Khi có nhiều toán tử, cần xác định độ ưu tiên và tính kết hợp. Nếu người đọc không chắc biểu thức được nhóm như thế nào, nên dùng ngoặc hoặc cấu trúc điều kiện tường minh.

Ví dụ:

```text
when (environment == "production" and replicas >= 3) {
    require approval from "release-manager"
}
```

Ngoặc làm rõ rằng cả hai điều kiện phải đúng. Nếu DSL có toán tử `and`, `or` và `not`, đặc tả cần xác định thứ tự đánh giá và hành vi short-circuit nếu có.

### 4.1. Tránh dựa vào quy tắc ưu tiên khó nhớ

Một biểu thức như:

```text
enabled and production or emergency
```

có thể được hiểu là `(enabled and production) or emergency` hoặc `enabled and (production or emergency)` nếu người đọc không nhớ quy tắc ưu tiên. Khi biểu thức ảnh hưởng đến quyền, triển khai hoặc quyết định nghiệp vụ, nên viết rõ:

```text
(enabled and production) or emergency
```

Hoặc tách thành các điều kiện có tên:

```text
isAllowed = enabled and production
mayProceed = isAllowed or emergency
```

### 4.2. Dùng toán tử theo ngữ nghĩa miền

Không nên tạo ký hiệu ngắn chỉ vì có thể. Nếu `in`, `contains`, `startsWith` hoặc `matches` thể hiện rõ ý nghĩa hơn một ký hiệu tự chế, hãy ưu tiên dạng dễ đọc. Với biểu thức có tính toán phức tạp, cần định nghĩa rõ kiểu dữ liệu và cách xử lý giá trị null hoặc thiếu.

Ví dụ, `user.roles contains "admin"` thường dễ hiểu hơn một lời gọi hàm có tên chung chung như `check(user, 7)`. Tuy nhiên, nếu DSL được dùng chủ yếu bởi lập trình viên và cú pháp biểu thức quen thuộc đã đủ rõ, toán tử chuẩn có thể ngắn gọn và dễ đọc hơn.

## 5. Thể hiện rõ dữ liệu, literal và đơn vị

Các giá trị trong DSL nên có hình thức dễ nhận biết. Chuỗi, số, boolean, ngày giờ, đường dẫn và định danh cần có quy tắc biểu diễn ổn định.

```text
service "orders-api" {
    replicas = 3
    enabled = true
    startup_timeout = 45s
    memory = "512Mi"
    created_after = 2026-01-01
}
```

Người đọc có thể nhận ra số bản sao là số nguyên, `enabled` là boolean, thời gian có đơn vị giây và bộ nhớ có đơn vị MiB. Nếu một giá trị cần đơn vị, nên thể hiện đơn vị trong cú pháp hoặc quy định rõ đơn vị mặc định. Tránh để người dùng đoán `timeout = 30` là 30 giây, 30 mili giây hay 30 phút.

### 5.1. Phân biệt giá trị mặc định, thiếu và null

Ba trạng thái này có thể mang ý nghĩa khác nhau:

- **Không khai báo**: người dùng không cung cấp giá trị; hệ thống có thể áp dụng mặc định.
- **Null**: người dùng chủ động chỉ định không có giá trị, nếu DSL hỗ trợ khái niệm này.
- **Giá trị mặc định tường minh**: người dùng yêu cầu một giá trị cụ thể giống hoặc khác mặc định hiện tại.

Ví dụ, nếu `replicas` không được khai báo thì mặc định là 1. Nếu DSL hỗ trợ `replicas = null`, cần nói rõ null có nghĩa là tự động quyết định, kế thừa từ môi trường hay xóa cấu hình. Không nên để cùng một cú pháp có nhiều cách hiểu theo từng công cụ.

### 5.2. Hạn chế chuỗi không có cấu trúc

Nếu một giá trị có cấu trúc rõ, nên cung cấp cú pháp để thể hiện cấu trúc đó. Ví dụ, danh sách cổng nên là danh sách số thay vì chuỗi phân tách bằng dấu phẩy:

```text
ports = [8080, 8443]
```

Điều này giúp parser kiểm tra từng phần tử, formatter trình bày nhất quán và công cụ hỗ trợ hoàn thành giá trị. Chuỗi tự do vẫn phù hợp cho nội dung thực sự là văn bản như mô tả hoặc thông điệp.

## 6. Cân bằng giữa ngắn gọn và tường minh

Một cú pháp ngắn có thể giảm số ký tự phải gõ nhưng làm tăng lượng kiến thức ngầm mà người đọc cần có. Ngược lại, lặp lại quá nhiều từ khóa khiến chương trình dài và nặng nề.

So sánh:

```text
svc "orders" img "example/orders:2.4" rep 3 port 8080
```

và:

```text
service "orders-api" {
    image = "example/orders:2.4"
    replicas = 3
    expose port 8080
}
```

Dạng thứ hai dài hơn nhưng tự mô tả tốt hơn. Người đọc không phải học rằng `svc`, `img` và `rep` là viết tắt của khái niệm nào. Với file được review, lưu trữ lâu dài hoặc dùng bởi nhiều nhóm, tính tường minh thường có giá trị cao.

Tuy nhiên, không phải mọi từ khóa đều cần lặp lại. Một danh sách ngắn có thể dùng cú pháp gọn nếu ngữ cảnh đã rõ:

```text
ports = [8080, 8443]
```

Nguyên tắc thực tế là giữ cú pháp ngắn ở nơi ý nghĩa đã rõ và dùng cấu trúc tường minh ở nơi có nhiều cách hiểu hoặc nơi quyết định có tác động lớn.

## 7. Giữ nhất quán trong toàn bộ ngôn ngữ

Người dùng học DSL bằng cách nhận ra quy luật. Khi cùng một loại thao tác có cú pháp giống nhau, họ có thể dự đoán cách viết cấu trúc mới. Khi quy tắc thay đổi tùy tiện, họ phải nhớ từng ngoại lệ.

Những điểm nên thống nhất gồm:

- Cách khai báo khối và kết thúc khối.
- Cách gán thuộc tính và truyền tham số.
- Cách viết danh sách, map và biểu thức.
- Quy tắc đặt tên cho hành động, sự kiện, trạng thái và thuộc tính.
- Cách ghi chú thích và chú thích nhiều dòng.
- Quy tắc chữ hoa, chữ thường và từ khóa dành riêng.
- Cách viết giá trị mặc định, thời gian, đơn vị và đường dẫn.

Ví dụ, nếu thuộc tính thông thường dùng dấu `=`, không nên có thuộc tính tương tự lại dùng dấu `:` mà không có lý do ngữ nghĩa. Nếu các khối đều dùng `{}` thì không nên dùng một loại dấu kết thúc khác cho một khối chỉ vì lịch sử triển khai.

### 7.1. Quy ước đặt tên

Chọn một kiểu đặt tên cho định danh, chẳng hạn `lower_snake_case` hoặc `camelCase`, rồi áp dụng nhất quán. Từ khóa dành riêng nên có danh sách rõ ràng; tên người dùng định nghĩa không nên xung đột với từ khóa hoặc tên hàm tích hợp.

Nếu DSL có phân biệt chữ hoa và chữ thường, cần thể hiện rõ trong tài liệu và thông báo lỗi. Nếu không phân biệt, formatter nên chuẩn hóa một cách viết để tránh cùng một định danh xuất hiện dưới nhiều hình thức.

### 7.2. Quy ước dấu câu và xuống dòng

Nên xác định dấu phẩy, dấu chấm phẩy, dấu ngoặc và khoảng trắng có vai trò gì. Nếu dấu phẩy là bắt buộc giữa các phần tử danh sách, parser cần báo thiếu dấu phẩy rõ ràng. Nếu cho phép dấu phẩy cuối danh sách, formatter nên giữ một kiểu nhất quán.

Với DSL dạng văn bản, thường nên cho phép xuống dòng và thụt lề để cải thiện khả năng đọc mà không làm thay đổi ý nghĩa. Nếu ngôn ngữ dùng indentation để xác định khối như một số ngôn ngữ lập trình, quy tắc tab, space và độ sâu thụt lề cần được đặc tả chính xác.

## 8. Dùng khoảng trắng, dòng trống và chú thích có chủ đích

Khoảng trắng có thể giúp chia chương trình thành các phần dễ quét. Một khối nên nhóm các khai báo liên quan; dòng trống có thể tách nhóm cấu hình; chú thích nên giải thích lý do hoặc quy tắc khó suy ra từ mã.

Ví dụ:

```text
service "orders-api" {
    # Runtime image used for this release.
    image = "example/orders:2.4"
    replicas = 3

    # Requests and limits for each instance.
    resources {
        cpu = "500m"
        memory = "512Mi"
    }

    health_check {
        path = "/health"
        interval = 10s
    }
}
```

Chú thích tốt bổ sung thông tin mà tên hoặc giá trị không thể hiện, chẳng hạn vì sao một ngưỡng được chọn hoặc vì sao một ngoại lệ nghiệp vụ tồn tại. Chú thích chỉ lặp lại câu lệnh như `# Set replicas to 3` ít giúp ích khi chính dòng lệnh đã thể hiện điều đó.

Không nên yêu cầu người dùng phải tự căn chỉnh thủ công để chương trình hợp lệ nếu có thể để formatter đảm nhận. Một formatter chuẩn giúp nhiều người viết cùng một DSL có phong cách thống nhất và làm diff dễ review hơn.

## 9. Cú pháp và thông báo lỗi có thể hiểu được

Độ dễ đọc không chỉ thể hiện ở chương trình hợp lệ. Khi người dùng mắc lỗi, công cụ cần giải thích vấn đề bằng thuật ngữ của DSL và chỉ ra vị trí liên quan.

Thông báo chung chung:

```text
Parse error at line 8
```

Thông báo hữu ích hơn:

```text
line 8, column 5: expected an integer after 'replicas', but found "three".
Use a number, for example: replicas = 3
```

Một thông báo lỗi tốt thường gồm:

1. Vị trí lỗi: file, dòng và cột hoặc vùng ký tự.
2. Điều parser hoặc validator mong đợi.
3. Giá trị hoặc cấu trúc thực tế gây lỗi.
4. Gợi ý sửa khi có thể xác định chắc chắn.

Phân biệt lỗi cú pháp và lỗi ngữ nghĩa cũng giúp người dùng hiểu vấn đề. Thiếu dấu `}` là lỗi cú pháp; tham chiếu đến một service không tồn tại có thể là lỗi ngữ nghĩa. Công cụ nên tránh báo một lỗi thứ cấp ở cuối file khi nguyên nhân thực sự nằm ở một khối chưa đóng trước đó.

## 10. Ví dụ: từ cú pháp khó đọc đến cú pháp rõ ràng

Giả sử DSL cần mô tả việc triển khai một dịch vụ với điều kiện chỉ triển khai lên production khi có ít nhất ba bản sao và đã được phê duyệt.

Một cách viết quá ngắn và phụ thuộc vào quy ước ngầm:

```text
svc orders prod 3 ok true img "orders:2.4"
```

Người đọc không biết `prod` là môi trường hay cờ bật, `3` là số bản sao hay số cổng, và `ok true` có nghĩa là đã được phê duyệt hay kiểm tra sức khỏe.

Cú pháp tường minh hơn:

```text
service "orders-api" {
    environment = "production"
    image = "example/orders:2.4"
    replicas = 3

    approval required from "release-manager"

    health_check {
        path = "/health"
        interval = 10s
    }
}
```

Nếu có quy tắc điều kiện, có thể khai báo riêng:

```text
when environment == "production" {
    require replicas >= 3
    require approval from "release-manager"
}
```

Hai phần có vai trò rõ ràng: khối `service` mô tả cấu hình dịch vụ; khối `when` mô tả điều kiện và yêu cầu áp dụng. Người đọc có thể review từng nhóm và công cụ có thể kiểm tra từng quy tắc.

## 11. Đặc tả grammar hỗ trợ khả năng đọc

Grammar là mô tả hình thức về cách các thành phần cú pháp được kết hợp. Một grammar rõ ràng giúp parser hoạt động nhất quán và là tài liệu tham chiếu cho người xây dựng công cụ.

Ví dụ EBNF rút gọn cho khai báo dịch vụ:

```ebnf
serviceDecl = "service", string, "{", { serviceMember }, "}" ;

serviceMember = imageDecl
              | replicasDecl
              | exposeDecl
              | healthCheckDecl ;

imageDecl = "image", "=", string ;
replicasDecl = "replicas", "=", integer ;
exposeDecl = "expose", "port", integer ;

healthCheckDecl = "health_check", "{",
                  "path", "=", string,
                  "interval", "=", duration,
                  "}" ;
```

Grammar cho biết thành phần nào có thể xuất hiện bên trong `service`, từ khóa nào bắt buộc và kiểu dữ liệu của một số giá trị. Các quy tắc như `replicas` phải lớn hơn 0 hoặc `path` phải bắt đầu bằng `/` thường cần kiểm tra ở bước ngữ nghĩa.

Một grammar dễ bảo trì nên tránh các quy tắc quá rộng khiến parser chấp nhận nhiều cấu trúc không có ý nghĩa. Nếu một từ khóa có thể xuất hiện ở nhiều vị trí với ngữ nghĩa khác nhau, cần cân nhắc đổi tên hoặc giới hạn ngữ cảnh để chương trình dễ hiểu hơn.

## 12. Formatter và quy ước trình bày

Khi nhiều người cùng viết DSL, chỉ tài liệu hóa phong cách có thể chưa đủ. Formatter tự động giúp chuẩn hóa thụt lề, khoảng trắng, dấu phẩy, xuống dòng và cách trình bày biểu thức.

Ví dụ, hai đoạn sau có thể mang cùng ý nghĩa:

```text
service "orders-api" { image="example/orders:2.4"; replicas=3; expose port 8080 }
```

```text
service "orders-api" {
    image = "example/orders:2.4"
    replicas = 3
    expose port 8080
}
```

Formatter có thể chuyển dạng đầu thành dạng thứ hai theo một quy tắc chuẩn. Điều này giúp review tập trung vào thay đổi ngữ nghĩa thay vì khác biệt trình bày.

Để formatter đáng tin cậy, cần xác định:

- Formatter có giữ nguyên chú thích và vị trí tương đối của chúng không?
- Formatter có chuẩn hóa thứ tự khai báo không, hay chỉ chuẩn hóa khoảng trắng?
- Có bảo toàn các dòng trống mà người viết dùng để chia nhóm không?
- Khi gặp cú pháp lỗi, formatter từ chối toàn bộ file hay định dạng phần hợp lệ?
- Kết quả định dạng có ổn định qua nhiều lần chạy không?

Một formatter tốt nên có tính ổn định: định dạng file đã chuẩn hóa thêm lần nữa không làm thay đổi kết quả. Nếu formatter sắp xếp lại khai báo, chỉ nên làm vậy khi thứ tự khai báo không mang ý nghĩa và việc sắp xếp không gây bất ngờ.

## 13. Cân nhắc khả năng đọc và khả năng mở rộng

Khi DSL phát triển, các từ khóa mới và cú pháp mới có thể làm tăng độ phức tạp. Thiết kế ban đầu nên dành chỗ cho mở rộng có kiểm soát, nhưng không cần dự đoán mọi tính năng tương lai.

Một số nguyên tắc hữu ích:

- Dành một không gian tên rõ ràng cho từ khóa dành riêng và tên người dùng định nghĩa.
- Ưu tiên thêm cấu trúc mới có thể hiểu độc lập thay vì thay đổi ý nghĩa cấu trúc cũ.
- Tránh thêm alias cú pháp nếu chúng không giải quyết nhu cầu cụ thể.
- Có quy tắc phiên bản khi thay đổi cú pháp hoặc ngữ nghĩa ảnh hưởng đến chương trình cũ.
- Cung cấp cảnh báo và công cụ chuyển đổi khi một cú pháp cũ sắp bị loại bỏ.
- Kiểm tra rằng cú pháp mới không tạo ra cách phân tích mơ hồ với cú pháp đã có.

Nếu DSL hỗ trợ extension hoặc plugin, cần xác định cách extension khai báo từ khóa, kiểu và hành vi để tránh xung đột. Một extension không nên âm thầm thay đổi cách hiểu của chương trình đã tồn tại.

## 14. Quy trình thiết kế và đánh giá cú pháp dễ đọc

Có thể triển khai việc thiết kế cú pháp theo các bước sau:

1. **Xác định người đọc và người viết**: ghi rõ kỹ năng, nhiệm vụ và ngữ cảnh sử dụng của từng nhóm.
2. **Thu thập ví dụ nghiệp vụ**: lấy các tình huống thật, bao gồm trường hợp phổ biến và ngoại lệ.
3. **Lập từ vựng miền**: thống nhất tên thực thể, hành động, sự kiện, trạng thái và thuộc tính.
4. **Phác thảo nhiều cách biểu đạt**: thử dạng tường minh, dạng gọn và dạng lồng nhau.
5. **Định nghĩa grammar và ngữ nghĩa**: xác định cấu trúc hợp lệ, kiểu dữ liệu, độ ưu tiên và ràng buộc.
6. **Viết ví dụ và phản ví dụ**: thể hiện cả cách dùng đúng và lỗi thường gặp.
7. **Thử đọc với người dùng mục tiêu**: yêu cầu họ giải thích chương trình và chỉnh sửa một tình huống mà không cần hướng dẫn từng dòng.
8. **Xây dựng parser, diagnostics và formatter**: kiểm tra rằng công cụ hỗ trợ đúng quy ước đã chọn.
9. **Điều chỉnh theo phản hồi**: sửa những từ khóa khó hiểu, cấu trúc khó đoán hoặc lỗi khó chẩn đoán.

Khi đánh giá, có thể quan sát thời gian người dùng cần để hiểu một ví dụ, số lần họ phải tra cứu tài liệu, khả năng dự đoán kết quả và số lỗi do hiểu sai cú pháp. Các phép đo này nên dựa trên tác vụ thật thay vì chỉ hỏi người dùng xem họ có thích cú pháp hay không.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Tác động | Cách cải thiện |
|---|---|---|
| Dùng quá nhiều từ viết tắt | Người đọc phải ghi nhớ quy ước ngầm | Dùng tên miền đầy đủ ở vị trí quan trọng |
| Một khái niệm có nhiều tên | Khó học và khó tìm kiếm | Chuẩn hóa thuật ngữ và từ khóa |
| Cấu trúc lồng nhau quá sâu | Khó quét và khó nhận ra phạm vi | Nhóm theo khái niệm, giảm cấp không cần thiết |
| Dựa vào độ ưu tiên toán tử khó nhớ | Biểu thức dễ bị hiểu sai | Dùng ngoặc hoặc điều kiện có tên |
| Giá trị không có đơn vị rõ ràng | Có thể gây cấu hình sai | Gắn đơn vị hoặc quy định mặc định tường minh |
| Trộn nhiều quy ước dấu câu | Người viết khó dự đoán grammar | Thống nhất cú pháp cho cùng loại cấu trúc |
| Cú pháp phụ thuộc vào khoảng trắng nhưng không được nói rõ | File có thể phân tích khác mong đợi | Đặc tả chính xác vai trò của whitespace và indentation |
| Thông báo lỗi chung chung | Khó tìm vị trí và nguyên nhân | Hiển thị vị trí, kỳ vọng và gợi ý sửa |
| Formatter làm thay đổi thứ tự có ý nghĩa | Có thể thay đổi hành vi chương trình | Chỉ chuẩn hóa thứ tự khi ngữ nghĩa cho phép |

## 16. Tiêu chí thực tế của một cú pháp dễ đọc

Một cú pháp có thể xem là dễ đọc khi người dùng mục tiêu có thể trả lời nhanh các câu hỏi sau chỉ bằng cách đọc chương trình:

- Chương trình đang mô tả đối tượng hoặc quy trình nào?
- Mỗi thuộc tính, điều kiện và hành động thuộc phạm vi nào?
- Giá trị nào là bắt buộc, giá trị nào là tùy chọn và đơn vị của chúng là gì?
- Những điều kiện nào quyết định hành vi?
- Có những bước hoặc thành phần nào phụ thuộc lẫn nhau?
- Nếu cần sửa một yêu cầu, phần nào của chương trình cần thay đổi?

Nếu người đọc phải mở mã nguồn parser hoặc hỏi tác giả mới hiểu một khai báo thông thường, cú pháp hoặc tài liệu của DSL cần được xem xét lại. Ngược lại, cú pháp không cần mô phỏng hoàn toàn ngôn ngữ tự nhiên; nó cần đủ chính xác để con người hiểu và máy móc kiểm tra được.

Một DSL có cú pháp dễ đọc khi từ vựng phản ánh miền, cấu trúc thể hiện đúng quan hệ, quy tắc nhất quán và công cụ hỗ trợ người dùng trong cả lúc viết lẫn lúc sửa lỗi. Những đặc điểm này giúp chương trình DSL trở thành một bản mô tả có thể trao đổi, review và bảo trì lâu dài.
