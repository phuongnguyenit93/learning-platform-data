# Khái niệm trung tâm của ngôn ngữ chuyên biệt miền

Ngôn ngữ chuyên biệt miền (Domain-Specific Language, viết tắt là **DSL**) là ngôn ngữ được thiết kế để mô tả một nhóm vấn đề, quy tắc hoặc công việc thuộc về một miền kiến thức cụ thể. Để hiểu và thiết kế DSL đúng cách, trước hết cần xác định miền mà ngôn ngữ phục vụ: những khái niệm nào tồn tại trong miền, ai sử dụng chúng, các quy tắc nào chi phối chúng và công việc nào cần được biểu đạt.

Trong chủ đề này, **phạm vi miền** là ranh giới của thế giới nghiệp vụ hoặc kỹ thuật mà DSL muốn mô hình hóa. Phạm vi ấy quyết định từ vựng, cấu trúc câu lệnh, ý nghĩa của chương trình DSL và cả những việc ngôn ngữ chủ động không cho phép diễn đạt. Một DSL có cú pháp đẹp nhưng không phản ánh đúng phạm vi miền sẽ buộc người dùng suy nghĩ theo cách của máy tính thay vì theo cách họ giải quyết vấn đề.

## 1. Miền (domain)

**Miền** là một lĩnh vực hoạt động hoặc tri thức có những khái niệm, đối tượng, quy tắc và mục tiêu riêng. Miền có thể thuộc nghiệp vụ, khoa học hoặc kỹ thuật.

Ví dụ:

- Trong thương mại điện tử, miền có thể gồm sản phẩm, giỏ hàng, đơn hàng, thanh toán, hoàn tiền và quy tắc khuyến mãi.
- Trong quản trị hạ tầng, miền có thể gồm máy chủ, mạng, vùng triển khai, tài nguyên, phụ thuộc và chính sách truy cập.
- Trong xử lý dữ liệu, miền có thể gồm bảng, trường, phép lọc, phép nối, phép nhóm và phép tổng hợp.
- Trong thiết kế giao diện, miền có thể gồm thành phần, bố cục, màu sắc, kiểu chữ, trạng thái và điểm ngắt màn hình.

Miền không đồng nghĩa với một ứng dụng, một ngôn ngữ lập trình hay một công nghệ triển khai. Một ứng dụng bán hàng có thể chứa nhiều miền khác nhau như quản lý kho, thanh toán và vận chuyển. Ngược lại, một miền như lập lịch có thể xuất hiện trong nhiều ứng dụng và được triển khai bằng nhiều công nghệ.

DSL được xây dựng quanh miền và nhiệm vụ của người dùng trong miền đó. Vì vậy, câu hỏi đầu tiên không phải là “nên dùng cú pháp nào?” mà là “người dùng đang cần mô tả hoặc giải quyết loại vấn đề nào?”.

### 1.1. Xác định ranh giới miền

Ranh giới miền cho biết phần nào của thế giới thực được DSL mô hình hóa. Ranh giới quá rộng làm ngôn ngữ phình to, có nhiều khái niệm không liên quan và khó học. Ranh giới quá hẹp khiến người dùng phải chuyển qua lại giữa DSL và mã nguồn thông thường cho những bước vốn thuộc cùng một quy trình.

Khi xác định ranh giới, hãy làm rõ:

1. **Mục tiêu:** DSL giúp người dùng mô tả, kiểm tra, truy vấn hay tự động hóa việc gì?
2. **Người dùng:** Người viết DSL là chuyên gia miền, lập trình viên, quản trị viên hay nhiều nhóm cùng tham gia?
3. **Đối tượng:** Những thực thể, giá trị, tài nguyên hoặc sự kiện nào cần được biểu diễn?
4. **Quy tắc:** Những điều kiện, giới hạn, bất biến và chính sách nào quyết định hành vi hợp lệ?
5. **Tác vụ:** Người dùng thường thực hiện những thao tác nào, theo trình tự nào?
6. **Ngoài phạm vi:** Những việc nào nên được giao cho ngôn ngữ lập trình tổng quát, hệ thống khác hoặc quy trình bên ngoài?

Phần “ngoài phạm vi” quan trọng không kém phần “trong phạm vi”. Ví dụ, một DSL mô tả chính sách vận chuyển có thể cho phép khai báo khu vực giao hàng, giới hạn khối lượng và cách tính phụ phí. Nó không nhất thiết phải mô tả giao thức mạng, giao diện quản trị hay cách lưu dữ liệu vào cơ sở dữ liệu.

### 1.2. Miền và ngữ cảnh giới hạn

Trong thiết kế phần mềm theo hướng miền (Domain-Driven Design, DDD), **bounded context** (ngữ cảnh giới hạn) là ranh giới trong đó một mô hình và từ vựng miền có ý nghĩa nhất quán. Đây là một khái niệm hữu ích khi xác định phạm vi DSL, dù không phải DSL nào cũng cần được tổ chức theo DDD.

Một từ có thể mang nghĩa khác nhau ở những ngữ cảnh khác nhau. Chẳng hạn, “tài khoản” trong miền thanh toán có thể là phương tiện ghi nhận số dư; trong miền đăng nhập, nó có thể là danh tính dùng để xác thực. Nếu một DSL cố gắng gộp hai ý nghĩa này vào cùng một khái niệm mà không phân biệt ngữ cảnh, câu lệnh dễ trở nên mơ hồ.

Khi miền có nhiều ngữ cảnh, có thể thiết kế các DSL riêng, các phần ngôn ngữ có ranh giới rõ ràng hoặc một ngôn ngữ chung có mô-đun. Lựa chọn phụ thuộc vào việc các ngữ cảnh có chia sẻ cùng mô hình và quy tắc hay không.

## 2. Mô hình miền (domain model)

**Mô hình miền** là cách biểu diễn có cấu trúc các khái niệm và quy tắc quan trọng trong miền. Nó đóng vai trò cầu nối giữa hiểu biết của chuyên gia miền và cấu trúc mà DSL cung cấp cho người viết.

Một mô hình miền thường bao gồm:

- **Thực thể (entity):** Đối tượng có danh tính và vòng đời, chẳng hạn đơn hàng hoặc tuyến giao hàng.
- **Đối tượng giá trị (value object):** Giá trị được xác định bởi nội dung của nó, chẳng hạn khoảng ngày, địa chỉ hoặc khối lượng.
- **Quan hệ:** Cách các khái niệm liên kết với nhau, chẳng hạn đơn hàng gồm nhiều dòng hàng.
- **Quy tắc nghiệp vụ:** Điều kiện quyết định hành vi hợp lệ, chẳng hạn đơn hàng chỉ được hoàn tiền khi đã thanh toán.
- **Sự kiện (event):** Điều đã xảy ra trong miền, chẳng hạn đơn hàng được xác nhận hoặc lô hàng đã giao.
- **Thao tác:** Hành động có ý nghĩa trong miền, chẳng hạn tính cước, phân bổ hàng hoặc áp dụng giảm giá.

Mô hình miền không nhất thiết trùng với lược đồ cơ sở dữ liệu hay cấu trúc lớp trong chương trình. Cơ sở dữ liệu mô tả cách lưu trữ; mô hình miền mô tả ý nghĩa và quy tắc. Một thực thể trong miền có thể được lưu bằng nhiều bảng, hoặc nhiều khái niệm miền có thể được biểu diễn trong cùng một cấu trúc lưu trữ.

DSL nên phơi bày những phần của mô hình mà người dùng cần thao tác. Không phải mọi chi tiết nội bộ đều cần xuất hiện trong ngôn ngữ. Ví dụ, người viết chính sách giao hàng cần khai báo khu vực, thời gian và mức phí; họ thường không cần biết hệ thống dùng cấu trúc chỉ mục nào để tìm tuyến phù hợp.

### 2.1. Quy tắc và bất biến miền

**Quy tắc miền** mô tả điều kiện hoặc hành vi có ý nghĩa nghiệp vụ. **Bất biến** là điều kiện phải luôn đúng trong trạng thái hợp lệ của mô hình.

Ví dụ:

- Khối lượng của một kiện hàng phải lớn hơn 0.
- Mức giảm giá không được vượt quá giới hạn được chính sách cho phép.
- Một khoảng thời gian phải có thời điểm kết thúc sau thời điểm bắt đầu.
- Một tuyến chỉ áp dụng cho những khu vực mà đơn vị vận chuyển phục vụ.

Các quy tắc này nên được thể hiện bằng khái niệm và thông báo lỗi thuộc miền. Thông báo “khối lượng kiện hàng phải lớn hơn 0 kg” giúp người dùng hiểu vấn đề hơn một lỗi kiểu dữ liệu chung chung như “giá trị không hợp lệ”.

## 3. Từ vựng miền và ngôn ngữ chung

**Từ vựng miền** là tập hợp các thuật ngữ mà người dùng và hệ thống dùng để nói về những khái niệm trong miền. Một DSL tốt sử dụng các từ mà người dùng miền nhận ra và hiểu theo cùng một nghĩa.

Trong DDD, **ubiquitous language** (ngôn ngữ chung) là hệ thống thuật ngữ được chuyên gia miền và nhóm phát triển sử dụng nhất quán trong trao đổi, mô hình và mã nguồn. DSL có thể biến ngôn ngữ chung này thành các cấu trúc cú pháp cụ thể.

Ví dụ, trong miền vận chuyển, các thuật ngữ có thể gồm `khu_vuc`, `khoang_cach`, `khoi_luong`, `thoi_gian_giao`, `phi_co_ban` và `phu_phi`. Nếu chuyên gia miền dùng từ “khu vực phục vụ”, DSL không nên tự ý gọi cùng khái niệm đó là “node” chỉ vì hệ thống nội bộ biểu diễn nó bằng một nút trong đồ thị.

Khi xây dựng từ vựng:

- Ưu tiên thuật ngữ đang được người dùng miền sử dụng.
- Định nghĩa rõ những từ gần nghĩa hoặc dễ nhầm lẫn.
- Tránh dùng một từ cho hai khái niệm khác nhau trong cùng ngữ cảnh.
- Dùng tên nhất quán trong tài liệu, cú pháp, thông báo lỗi và công cụ hỗ trợ.
- Chỉ đưa thuật ngữ kỹ thuật vào DSL khi người dùng thực sự cần thao tác với khái niệm kỹ thuật đó.

Từ vựng rõ ràng giúp DSL dễ đọc, nhưng từ ngữ quen thuộc vẫn cần ngữ nghĩa chính xác. Một từ như “ưu tiên” có thể chỉ thứ tự xét quy tắc, mức độ quan trọng hoặc quyền được xử lý trước. Tài liệu DSL phải chỉ rõ ý nghĩa được chọn.

## 4. Ngôn ngữ chuyên biệt miền (DSL)

DSL là ngôn ngữ có **phạm vi biểu đạt được tối ưu cho một miền hoặc một họ nhiệm vụ**. Nó cung cấp các cấu trúc để người dùng diễn đạt ý định ở mức trừu tượng phù hợp với miền đó.

Ví dụ quen thuộc:

| Ngôn ngữ | Miền hoặc nhiệm vụ chính |
|---|---|
| SQL | Truy vấn và thao tác dữ liệu quan hệ |
| Regular expressions | Mô tả mẫu chuỗi và phép so khớp |
| CSS | Mô tả cách trình bày giao diện web |
| HTML | Mô tả cấu trúc nội dung tài liệu web |
| Terraform HCL | Khai báo hạ tầng và cấu hình tài nguyên |
| Makefile | Khai báo mục tiêu và phụ thuộc trong quy trình xây dựng |

Một DSL có thể nhỏ, chỉ gồm vài câu lệnh, hoặc có thể rất phong phú. Điều làm nó trở thành DSL không phải là số lượng từ khóa hay độ phức tạp của bộ phân tích cú pháp, mà là việc các cấu trúc ngôn ngữ được chọn để diễn đạt hiệu quả một miền cụ thể.

### 4.1. DSL và ngôn ngữ lập trình tổng quát

Ngôn ngữ lập trình tổng quát (General-Purpose Language, GPL) như Java, Python hoặc C# có thể giải quyết nhiều loại bài toán. DSL tập trung vào một phạm vi hẹp hơn và thường biểu đạt ý định miền trực tiếp hơn.

| Tiêu chí | DSL | Ngôn ngữ lập trình tổng quát |
|---|---|---|
| Phạm vi | Một miền hoặc họ nhiệm vụ | Nhiều miền và loại nhiệm vụ |
| Từ vựng | Gần khái niệm miền | Gần khái niệm tính toán và cấu trúc chương trình |
| Biểu đạt | Tối ưu cho tác vụ mục tiêu | Linh hoạt và có thể mở rộng rộng rãi |
| Người dùng | Có thể gồm chuyên gia không chuyên lập trình | Thường cần kiến thức lập trình |
| Khả năng tái sử dụng | Thường tập trung trong miền | Thường dùng cho nhiều loại hệ thống |

Đây là xu hướng chứ không phải ranh giới tuyệt đối. Một DSL vẫn có thể có biến, hàm, biểu thức hoặc kiểu dữ liệu. Một ngôn ngữ tổng quát cũng có thể cung cấp thư viện và cú pháp giúp giải quyết một miền thuận tiện hơn.

### 4.2. DSL không chỉ là một tệp cấu hình

Tệp cấu hình thường cung cấp giá trị cho các tùy chọn có sẵn, ví dụ bật/tắt tính năng hoặc đặt địa chỉ máy chủ. DSL có thể làm được nhiều hơn: nó có thể có quy tắc, biểu thức, cấu trúc lặp, quan hệ phụ thuộc và ngữ nghĩa thực thi riêng.

Tuy vậy, ranh giới giữa cấu hình và DSL không tuyệt đối. Một định dạng cấu hình có cấu trúc và ngữ nghĩa đủ phong phú cũng có thể được xem là DSL khai báo. Cách gọi tên ít quan trọng hơn việc hiểu chính xác người dùng được phép mô tả điều gì và hệ thống diễn giải mô tả đó ra sao.

## 5. Cú pháp và ngữ nghĩa

Hai thành phần cốt lõi của mọi ngôn ngữ là **cú pháp** và **ngữ nghĩa**.

- **Cú pháp (syntax)** quy định cách viết một biểu thức hoặc chương trình hợp lệ: từ khóa, dấu phân cách, thứ tự thành phần, quy tắc lồng nhau và cấu trúc câu lệnh.
- **Ngữ nghĩa (semantics)** quy định biểu thức hợp lệ có ý nghĩa gì và dẫn đến hành vi hoặc kết quả nào.

Ví dụ, câu lệnh `giam_gia 10%` có thể đúng cú pháp nếu ngôn ngữ cho phép khai báo mức giảm giá theo phần trăm. Nhưng ngữ nghĩa còn phải trả lời: giảm giá áp dụng cho sản phẩm hay toàn bộ đơn hàng, được tính trước hay sau thuế, và có giới hạn tối đa hay không.

Một chương trình có thể đúng cú pháp nhưng sai ngữ nghĩa miền. Chẳng hạn, `khoi_luong = -2 kg` có thể được bộ phân tích cú pháp chấp nhận vì nó nhận ra một số âm và một đơn vị đo, nhưng bộ kiểm tra miền phải từ chối vì khối lượng không thể âm trong mô hình đang xét.

### 5.1. Cú pháp cụ thể và cú pháp trừu tượng

**Cú pháp cụ thể (concrete syntax)** là hình thức người dùng nhìn thấy và viết ra. Nó bao gồm từ khóa, dấu ngoặc, dấu phẩy, cách thụt lề và cách biểu diễn giá trị.

**Cú pháp trừu tượng (abstract syntax)** là cấu trúc có ý nghĩa mà hệ thống rút ra sau khi phân tích văn bản. Cấu trúc này thường được biểu diễn bằng cây cú pháp trừu tượng (Abstract Syntax Tree, AST) hoặc một mô hình trung gian tương đương.

Ví dụ, hai cách viết sau có thể biểu đạt cùng một ý định nếu DSL định nghĩa chúng tương đương:

```text
phi_co_ban = 30000
phu_phi_km = 5000
```

```text
cuoc_phi {
    co_ban: 30000
    moi_km: 5000
}
```

Hình thức văn bản khác nhau, nhưng mô hình trừu tượng có thể cùng chứa một mức phí cơ bản và một mức phí theo kilomet. Tách cú pháp cụ thể khỏi mô hình trừu tượng giúp thay đổi cách viết mà không phải thay đổi toàn bộ logic miền.

### 5.2. Ngữ pháp

**Ngữ pháp (grammar)** mô tả các quy tắc kết hợp ký hiệu để tạo thành chương trình hợp lệ. Với DSL văn bản, ngữ pháp có thể được mô tả bằng EBNF, PEG hoặc một định dạng tương đương.

Ví dụ minh họa một ngữ pháp rút gọn:

```ebnf
policy       = "chinh_sach", identifier, "{", rule*, "}" ;
rule         = base_fee | distance_fee | free_shipping ;
base_fee     = "phi_co_ban", number, currency ;
distance_fee = "moi_km", number, currency ;
free_shipping = "mien_phi_khi", expression ;
```

Ngữ pháp cho biết một chính sách có tên và phần thân chứa các quy tắc phí. Nó chưa mô tả đầy đủ ý nghĩa nghiệp vụ, chẳng hạn đơn vị tiền tệ nào được hỗ trợ hoặc điều kiện miễn phí được đánh giá tại thời điểm nào. Những điều đó thuộc ngữ nghĩa và quy tắc kiểm tra miền.

## 6. Cách DSL được xử lý và thực thi

Sau khi người dùng viết DSL, hệ thống cần phân tích và biến nội dung thành một dạng có thể kiểm tra hoặc thực hiện. Một quy trình thường gặp gồm:

1. **Đọc đầu vào (lexing):** Chia văn bản thành các token như từ khóa, tên, số và ký hiệu.
2. **Phân tích cú pháp (parsing):** Kiểm tra cách token kết hợp theo ngữ pháp và tạo cấu trúc cú pháp.
3. **Kiểm tra ngữ nghĩa:** Xác minh tên có tồn tại, kiểu giá trị phù hợp, tham chiếu hợp lệ và quy tắc miền được thỏa mãn.
4. **Tạo mô hình trung gian:** Chuyển cấu trúc cú pháp thành mô hình miền hoặc biểu diễn trung gian thuận tiện cho xử lý.
5. **Thực thi hoặc chuyển đổi:** Diễn giải mô hình, biên dịch sang dạng khác, sinh mã hoặc tạo cấu hình cho hệ thống đích.

Không phải DSL nào cũng cần đủ các bước theo đúng hình thức trên. Một DSL nhỏ có thể được đọc trực tiếp bằng bộ phân tích đơn giản; một DSL lớn có thể cần nhiều giai đoạn và hệ thống kiểu dữ liệu.

### 6.1. DSL nhúng và DSL độc lập

**DSL nhúng (embedded DSL)** được xây dựng bên trong một ngôn ngữ chủ (host language). Nó tận dụng cú pháp, kiểu dữ liệu, hàm và công cụ của ngôn ngữ chủ để tạo cách viết gần với ngôn ngữ miền.

Ví dụ, một thư viện Java có thể cung cấp API dạng chuỗi lời gọi phương thức để mô tả truy vấn. Một DSL nhúng trong Kotlin có thể tận dụng lambda và các hàm mở rộng để tạo cấu trúc khai báo.

Ưu điểm của DSL nhúng là dễ tích hợp với hệ sinh thái hiện có, có thể tái sử dụng trình biên dịch và công cụ của ngôn ngữ chủ. Hạn chế là cú pháp vẫn bị ràng buộc bởi ngôn ngữ chủ; đôi khi người dùng phải chấp nhận dấu ngoặc, kiểu hoặc quy tắc không tự nhiên đối với miền.

**DSL độc lập (external DSL)** có cú pháp và bộ xử lý riêng, thường được viết trong tệp hoặc môi trường riêng. SQL và CSS là những ví dụ quen thuộc về ngôn ngữ có cú pháp riêng.

DSL độc lập cho phép kiểm soát tốt hơn trải nghiệm viết và thông báo lỗi, nhưng nhóm phát triển phải xây dựng hoặc tích hợp bộ phân tích, kiểm tra, tài liệu và công cụ hỗ trợ. Việc lựa chọn phụ thuộc vào độ phức tạp của miền, đối tượng người dùng và mức độ cần thiết của cú pháp riêng.

### 6.2. Diễn giải, biên dịch và sinh mã

DSL có thể được xử lý theo nhiều cách:

- **Diễn giải (interpretation):** Đọc mô hình DSL và trực tiếp thực hiện hành vi tương ứng.
- **Biên dịch (compilation):** Chuyển DSL thành một dạng thực thi khác, chẳng hạn bytecode hoặc mã của ngôn ngữ chủ.
- **Chuyển đổi (translation):** Chuyển DSL thành một ngôn ngữ hoặc định dạng khác, chẳng hạn SQL, JSON hay cấu hình của nền tảng đích.
- **Sinh mã (code generation):** Tạo mã nguồn hoặc tệp triển khai từ mô hình DSL.
- **Phân tích tĩnh:** Kiểm tra tính hợp lệ mà không cần thực thi hành động thật, ví dụ phát hiện quy tắc xung đột hoặc tài nguyên chưa được khai báo.

Những lựa chọn này không làm thay đổi bản chất miền của DSL. Chúng là quyết định triển khai về cách hiện thực ngữ nghĩa đã được định nghĩa.

## 7. Phạm vi biểu đạt của DSL

Phạm vi miền xác định DSL nói về điều gì; phạm vi biểu đạt xác định người dùng có thể mô tả những hành động và quan hệ nào trong miền đó.

Một DSL thường cần xác định rõ các khía cạnh sau:

### 7.1. Các khái niệm được hỗ trợ

Liệt kê đối tượng, thuộc tính, sự kiện, thao tác và quy tắc mà người dùng có thể khai báo. Chỉ thêm một khái niệm khi nó có ý nghĩa rõ ràng trong miền và phục vụ một tác vụ thực tế.

### 7.2. Các thao tác được phép

Quyết định DSL chỉ mô tả trạng thái mong muốn (khai báo), mô tả chuỗi hành động (mệnh lệnh), hay kết hợp cả hai. Ví dụ, một DSL hạ tầng khai báo “cần ba máy chủ” khác với DSL ra lệnh “tạo máy chủ thứ nhất, sau đó tạo máy chủ thứ hai”.

### 7.3. Các giới hạn và điều kiện

Định nghĩa miền giá trị, đơn vị đo, giới hạn số lượng, quan hệ phụ thuộc và điều kiện hợp lệ. Nếu DSL có kiểu dữ liệu cho tiền tệ, thời gian hoặc khoảng cách, cần quy định cách chuyển đổi và so sánh giữa các đơn vị.

### 7.4. Khả năng kết hợp

Người dùng có thể ghép các quy tắc hoặc mô-đun như thế nào? Các khai báo có thể kế thừa, ghi đè, tham chiếu hoặc tái sử dụng không? Nếu có, cần quy định thứ tự áp dụng và cách xử lý xung đột.

### 7.5. Những gì không được biểu đạt

Một DSL không cần trở thành ngôn ngữ lập trình đầy đủ. Nếu người dùng cần một thuật toán tùy ý, truy cập hệ thống tệp hoặc gọi dịch vụ bên ngoài, có thể cung cấp điểm mở rộng có kiểm soát hoặc giao việc đó cho ngôn ngữ chủ. Mở rộng phạm vi chỉ vì có thể làm được thường khiến ngôn ngữ khó hiểu và khó bảo đảm an toàn.

## 8. Ví dụ: DSL mô tả chính sách tính phí giao hàng

Giả sử một doanh nghiệp cần để nhân viên vận hành khai báo quy tắc tính phí giao hàng. Mục tiêu của DSL là mô tả chính sách theo các thuật ngữ mà nhân viên hiểu được, sau đó hệ thống dùng chính sách để tính cước cho đơn hàng.

Một đoạn DSL minh họa có thể viết như sau:

```text
chinh_sach giao_hang_noi_thanh {
    tien_te: VND
    phi_co_ban: 30000
    phi_moi_km: 5000

    mien_phi_khi {
        gia_tri_don_hang >= 500000
    }

    gioi_han_khoi_luong: 20 kg
    khu_vuc_ap_dung: noi_thanh
}
```

Đây là cú pháp giả định để giải thích khái niệm, không phải một ngôn ngữ đã có bộ phân tích thực thi. Cấu trúc trên thể hiện một số khái niệm miền:

- `chinh_sach` tạo một chính sách có tên.
- `tien_te` xác định đơn vị tiền được dùng trong chính sách.
- `phi_co_ban` và `phi_moi_km` biểu diễn các thành phần của công thức tính phí.
- `mien_phi_khi` chứa điều kiện áp dụng miễn phí.
- `gioi_han_khoi_luong` đặt giới hạn đối với kiện hàng.
- `khu_vuc_ap_dung` giới hạn phạm vi địa lý của chính sách.

### 8.1. Xác định điều gì thuộc miền

Các khái niệm “đơn hàng”, “giá trị đơn hàng”, “kilomet”, “khối lượng”, “khu vực” và “phí giao hàng” thuộc miền vận chuyển hoặc tính cước. Chúng nên xuất hiện trong DSL nếu nhân viên cần dùng chúng để tạo chính sách.

Các chi tiết như tên bảng lưu chính sách, câu lệnh SQL, địa chỉ máy chủ cơ sở dữ liệu hoặc thuật toán tối ưu truy vấn không thuộc phạm vi biểu đạt mà nhân viên vận hành cần thấy. Hệ thống triển khai có thể sử dụng những chi tiết đó ở bên dưới.

### 8.2. Xác định ngữ nghĩa

Để đoạn DSL trên có ý nghĩa chính xác, tài liệu ngôn ngữ cần quy định thêm:

- Phí được tính theo khoảng cách thực tế, khoảng cách đường chim bay hay khoảng cách do đơn vị vận chuyển cung cấp.
- Điều kiện miễn phí được xét trước hay sau khi áp dụng mã giảm giá.
- Đơn hàng đúng 500.000 VND có đủ điều kiện miễn phí hay không. Với toán tử `>=`, câu trả lời là có.
- Khối lượng vượt quá 20 kg sẽ bị từ chối, tính phụ phí hay chuyển sang chính sách khác.
- `noi_thanh` được định nghĩa ở đâu và gồm những địa điểm nào.
- Cách làm tròn kết quả và xử lý khi thiếu dữ liệu khoảng cách.

Nếu không định nghĩa những điểm này, hai hệ thống có thể phân tích cùng một DSL nhưng tính ra kết quả khác nhau. Đó là vấn đề ngữ nghĩa, không phải vấn đề trình bày cú pháp.

### 8.3. Kiểm tra hợp lệ

Một bộ kiểm tra DSL có thể phát hiện:

- `phi_co_ban` âm hoặc không phải kiểu tiền tệ hợp lệ.
- Đơn vị tiền không được hỗ trợ.
- `khu_vuc_ap_dung` tham chiếu đến khu vực chưa khai báo.
- `gioi_han_khoi_luong` có giá trị bằng 0 hoặc âm.
- Hai quy tắc cùng mức ưu tiên có điều kiện xung đột.
- Một điều kiện sử dụng thuộc tính không tồn tại trong mô hình đơn hàng.

Thông báo lỗi nên chỉ rõ vị trí, khái niệm và cách sửa. Ví dụ: “`gioi_han_khoi_luong` phải lớn hơn 0 kg” có ích hơn “validation failed”.

## 9. Phân biệt DSL với API, thư viện và định dạng dữ liệu

Những cơ chế này có thể cùng phục vụ một miền, nhưng cung cấp trải nghiệm và mức độ trừu tượng khác nhau.

| Cơ chế | Người dùng tương tác bằng cách nào? | Vai trò điển hình |
|---|---|---|
| DSL | Viết biểu thức hoặc khai báo theo cú pháp miền | Mô tả ý định và quy tắc của miền |
| API | Gọi hàm, phương thức hoặc endpoint theo hợp đồng | Tích hợp chức năng giữa các thành phần |
| Thư viện | Sử dụng mã đã đóng gói qua API | Tái sử dụng thuật toán và chức năng |
| Định dạng dữ liệu | Ghi dữ liệu theo cấu trúc như JSON hoặc YAML | Trao đổi và lưu trữ dữ liệu |
| Ngôn ngữ lập trình tổng quát | Viết thuật toán và cấu trúc điều khiển tổng quát | Xây dựng nhiều loại phần mềm |

Các ranh giới này có thể giao nhau. JSON hoặc YAML có thể được dùng làm cú pháp cho một DSL khai báo. Một API dạng fluent có thể tạo cảm giác như DSL nhúng. Một thư viện có thể cung cấp bộ diễn giải DSL. Vì vậy, cần xem xét ngữ nghĩa và mục tiêu sử dụng thay vì chỉ dựa vào phần mở rộng tệp hoặc hình thức câu lệnh.

## 10. Quy trình xác định và thiết kế phạm vi miền

Một quy trình thực tế có thể tiến hành theo các bước sau:

1. **Thu thập tình huống sử dụng:** Quan sát công việc thật, ví dụ chính sách nào thường được viết, ai viết, ai đọc và lỗi nào thường xảy ra.
2. **Chọn nhiệm vụ trọng tâm:** Xác định nhóm công việc lặp lại mà DSL cần làm tốt. Tránh bắt đầu bằng mong muốn tạo một ngôn ngữ “có thể làm mọi thứ”.
3. **Lập bản đồ khái niệm:** Ghi lại thực thể, giá trị, quan hệ, sự kiện, quy tắc và thuật ngữ của miền.
4. **Đặt ranh giới:** Ghi rõ những gì DSL hỗ trợ và những gì thuộc trách nhiệm của hệ thống hoặc công cụ khác.
5. **Thống nhất từ vựng:** Xác nhận cách gọi với chuyên gia miền; định nghĩa thuật ngữ có nhiều nghĩa hoặc dễ nhầm.
6. **Thiết kế cú pháp:** Chọn cách biểu diễn phù hợp với người dùng, khối lượng thông tin và công cụ biên tập.
7. **Định nghĩa ngữ nghĩa:** Mô tả chính xác cách mỗi cấu trúc được hiểu, kiểm tra và thực thi.
8. **Xây dựng bộ kiểm tra:** Phát hiện lỗi cú pháp, lỗi tham chiếu, sai kiểu và vi phạm quy tắc miền.
9. **Thử nghiệm với người dùng:** Dùng các ví dụ thật để xem người dùng có diễn đạt được ý định tự nhiên và dễ đọc lại hay không.
10. **Điều chỉnh có kiểm soát:** Chỉ thêm khái niệm hoặc cú pháp khi có nhu cầu miền rõ ràng; cập nhật tài liệu và kiểm thử tương ứng.

Các bước này có thể lặp lại. Khi thử nghiệm phát hiện người dùng phải dùng một thuật ngữ không đúng với cách họ làm việc, vấn đề có thể nằm ở mô hình miền hoặc ranh giới đã chọn, chứ không chỉ ở cách đặt tên.

## 11. Tiêu chí đánh giá một phạm vi DSL tốt

Một phạm vi DSL hợp lý thường có các đặc điểm sau:

- **Tập trung:** Các cấu trúc đều phục vụ một miền hoặc một nhóm nhiệm vụ liên quan.
- **Dễ hiểu:** Người dùng miền có thể đọc và giải thích chương trình mà không cần hiểu chi tiết triển khai.
- **Nhất quán:** Mỗi thuật ngữ và cấu trúc có ý nghĩa ổn định trong phạm vi đã chọn.
- **Đủ biểu đạt:** Người dùng hoàn thành được các tác vụ mục tiêu mà không phải liên tục thoát sang mã nguồn khác.
- **Có giới hạn:** Những hành vi ngoài phạm vi được nhận diện và xử lý có chủ đích.
- **Có thể kiểm tra:** Quy tắc miền có thể được xác minh trước khi thực thi hoặc triển khai.
- **Có thể phát triển:** Có cách mở rộng, phiên bản hóa và duy trì tương thích khi miền thay đổi.

Không có một cú pháp hoặc mức độ trừu tượng phù hợp cho mọi DSL. DSL dành cho chuyên gia kỹ thuật có thể chấp nhận biểu thức phức tạp; DSL dành cho nhân viên nghiệp vụ có thể cần cấu trúc khai báo rõ ràng và ít ký hiệu hơn. Tiêu chí quan trọng là mức độ phù hợp giữa ngôn ngữ, miền và người dùng.

## 12. Những sai lầm thường gặp khi xác định miền

### 12.1. Chọn phạm vi theo cấu trúc triển khai

Nếu DSL phản ánh trực tiếp tên bảng, lớp, endpoint hoặc cấu trúc nội bộ, người dùng phải hiểu cách hệ thống được xây dựng mới sử dụng được ngôn ngữ. Hãy bắt đầu từ khái niệm miền; ánh xạ sang cấu trúc triển khai ở lớp xử lý phía sau.

### 12.2. Trộn nhiều miền không nhất quán

Một DSL cố gắng mô tả thanh toán, vận chuyển, phân quyền và giao diện trong cùng một mô hình dễ tạo ra từ vựng mơ hồ và quy tắc chồng chéo. Hãy kiểm tra xem các phần đó có thực sự chia sẻ cùng một mô hình hay nên tách thành các ngữ cảnh hoặc mô-đun riêng.

### 12.3. Mô hình hóa quá mức

Đưa mọi khái niệm có thể tưởng tượng vào phiên bản đầu khiến DSL khó học và tăng chi phí bảo trì. Bắt đầu từ những tác vụ có tần suất hoặc giá trị cao, sau đó mở rộng dựa trên bằng chứng sử dụng.

### 12.4. Cú pháp đẹp nhưng ngữ nghĩa mơ hồ

Một câu lệnh ngắn gọn vẫn có thể dẫn đến cách hiểu khác nhau. Cần quy định thứ tự áp dụng, giá trị mặc định, phạm vi hiệu lực, cách xử lý xung đột và hành vi khi thiếu dữ liệu.

### 12.5. Không định nghĩa trường hợp lỗi

DSL phải nói rõ điều gì xảy ra khi tham chiếu không tồn tại, dữ liệu sai kiểu, điều kiện không thể thỏa mãn hoặc hai quy tắc mâu thuẫn. Phát hiện lỗi sớm và thông báo bằng ngôn ngữ miền giúp người dùng sửa chính xác.

### 12.6. Để DSL phụ thuộc quá chặt vào một nền tảng

Nếu khái niệm miền bị gắn với chi tiết riêng của một công cụ, việc đổi nền tảng có thể buộc người dùng viết lại toàn bộ DSL. Nên giữ mô hình miền ổn định khi có thể và đặt phần chuyển đổi sang nền tảng trong bộ xử lý.

## 13. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Domain (miền) | Lĩnh vực vấn đề hoặc tri thức mà ngôn ngữ phục vụ |
| Domain scope (phạm vi miền) | Ranh giới các khái niệm và nhiệm vụ thuộc trách nhiệm của DSL |
| Domain model (mô hình miền) | Biểu diễn có cấu trúc các khái niệm, quan hệ và quy tắc miền |
| Ubiquitous language (ngôn ngữ chung) | Từ vựng thống nhất giữa chuyên gia miền và nhóm phát triển |
| Bounded context (ngữ cảnh giới hạn) | Ranh giới mà trong đó một mô hình và từ vựng có ý nghĩa nhất quán |
| DSL | Ngôn ngữ được tối ưu để biểu đạt một miền hoặc họ nhiệm vụ cụ thể |
| Syntax (cú pháp) | Quy tắc về hình thức và cấu trúc của biểu thức |
| Semantics (ngữ nghĩa) | Ý nghĩa và hành vi của biểu thức hợp lệ |
| Grammar (ngữ pháp) | Quy tắc kết hợp ký hiệu để tạo cấu trúc hợp lệ |
| AST | Cây biểu diễn cấu trúc trừu tượng của chương trình |
| Embedded DSL | DSL được xây dựng bên trong một ngôn ngữ chủ |
| External DSL | DSL có cú pháp và bộ xử lý riêng |

Khi phân tích một DSL, hãy luôn nối ba câu hỏi với nhau: **ngôn ngữ phục vụ miền nào, người dùng cần diễn đạt điều gì trong miền đó, và hệ thống hiểu cũng như xử lý phần diễn đạt ấy ra sao?** Trả lời rõ ba câu hỏi này giúp xác định phạm vi miền trước khi đi sâu vào cú pháp hoặc công nghệ triển khai.
