# Backend và target

## 1. Backend và target trong kiến trúc DSL

Một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL) cần một thành phần biến mô tả do người dùng viết thành hành vi hoặc đầu ra mà hệ thống có thể sử dụng. Thành phần đảm nhiệm công việc này thường được gọi là **backend**. Backend tiếp nhận biểu diễn đã được phân tích và kiểm tra, sau đó diễn giải, thực thi, chuyển đổi hoặc sinh ra một sản phẩm phù hợp với môi trường đích.

**Target** là môi trường hoặc định dạng mà DSL hướng tới. Tùy bài toán, target có thể là:

- Một nền tảng chạy chương trình, chẳng hạn JVM, trình duyệt hoặc một runtime chuyên dụng.
- Một ngôn ngữ lập trình, chẳng hạn Java, Kotlin, JavaScript hoặc SQL.
- Một hệ thống thực thi, chẳng hạn workflow engine, rule engine hoặc nền tảng điều phối.
- Một định dạng dữ liệu hoặc cấu hình, chẳng hạn JSON, YAML, XML hay một schema.
- Một giao thức hoặc dịch vụ bên ngoài mà DSL cần tạo yêu cầu.

Hai thuật ngữ có liên hệ chặt chẽ nhưng không đồng nghĩa. Backend là thành phần hoặc chiến lược xử lý; target là nơi hoặc hình thức mà kết quả hướng tới. Ví dụ, một backend sinh mã Java có thể nhắm đến JVM; một backend khác có thể diễn giải cùng mô hình miền trực tiếp trong ứng dụng. Trong một số kiến trúc, backend và target được ghép thành một cặp cố định; trong kiến trúc khác, một backend có thể hỗ trợ nhiều target.

Khi thiết kế DSL, cần trả lời hai câu hỏi riêng:

1. **DSL cần tạo ra hoặc thực hiện điều gì?** Đây là quyết định về hành vi và sản phẩm đầu ra.
2. **Hành vi đó sẽ được xử lý ở đâu và bằng cách nào?** Đây là quyết định về backend và target.

Nếu chưa làm rõ hai câu hỏi này, nhóm có thể thiết kế cú pháp đẹp nhưng không biết mô tả sẽ được thực thi, chuyển đổi hay tích hợp vào hệ thống nào.

## 2. Vị trí của backend trong pipeline DSL

Một kiến trúc DSL thường có các giai đoạn từ văn bản nguồn đến kết quả. Tên gọi và cách chia module có thể khác nhau, nhưng luồng xử lý thường gồm:

1. **Nguồn DSL:** văn bản hoặc cấu hình do người dùng tạo.
2. **Lexer và parser:** nhận diện token và cấu trúc cú pháp.
3. **AST:** biểu diễn cấu trúc cú pháp dưới dạng cây.
4. **Phân tích ngữ nghĩa:** kiểm tra tên, kiểu, phạm vi, quy tắc và tính hợp lệ theo miền.
5. **IR:** biểu diễn trung gian đã chuẩn hóa để backend có thể xử lý.
6. **Backend:** diễn giải IR, thực thi hoặc chuyển IR thành đầu ra khác.
7. **Target/runtime:** nơi đầu ra được chạy, nạp, lưu trữ hoặc gửi đến.

Luồng khái quát:

~~~text
Nguồn DSL
   |
   v
Lexer / Parser
   |
   v
AST
   |
   v
Phân tích ngữ nghĩa
   |
   v
IR đã kiểm tra
   |
   +--------------------+
   |          |         |
   v          v         v
Backend A  Backend B  Backend C
   |          |         |
   v          v         v
Java/JVM    SQL       JSON config
   |          |         |
   v          v         v
Ứng dụng   Database   Hệ thống đích
~~~

Backend thường bắt đầu sau khi cấu trúc và ý nghĩa của DSL đã được xác định. Điều này cho phép nhiều backend dùng chung parser, mô hình miền và quy tắc kiểm tra. Nếu mỗi backend tự phân tích văn bản nguồn theo cách riêng, các target có thể hiểu cùng một DSL khác nhau.

Không phải kiến trúc nào cũng cần một IR riêng. Với DSL nhỏ, AST đã kiểm tra có thể được backend sử dụng trực tiếp. Với DSL lớn hoặc nhiều target, IR tách biệt thường giúp giảm phụ thuộc vào chi tiết cú pháp và làm rõ ngữ nghĩa mà các backend phải bảo toàn.

## 3. Các kiểu backend thường gặp

Backend được chọn theo cách DSL cần được sử dụng. Một số kiểu phổ biến có thể kết hợp với nhau.

### 3.1 Interpreter — backend diễn giải

Interpreter đọc AST hoặc IR và trực tiếp thực hiện các thao tác tương ứng. Nó không nhất thiết sinh mã nguồn hay file chương trình khác.

Ví dụ, một DSL mô tả điều kiện định tuyến có thể được interpreter duyệt qua từng quy tắc, đánh giá điều kiện với dữ liệu của yêu cầu và trả về đích xử lý.

Ưu điểm:

- Có thể triển khai nhanh cho DSL có phạm vi nhỏ hoặc trung bình.
- Dễ gắn với đối tượng và dịch vụ của ứng dụng hiện tại.
- Có thể cung cấp thông báo lỗi gắn với từng biểu thức DSL.
- Không cần quy trình biên dịch ra ngôn ngữ khác.

Hạn chế:

- Mỗi lần thực thi có thể phải duyệt và đánh giá lại biểu diễn.
- Hiệu năng phụ thuộc vào interpreter và cách tối ưu.
- Việc triển khai trực tiếp có thể khiến ngữ nghĩa DSL gắn chặt với runtime của ứng dụng.

Interpreter phù hợp khi mô tả được nạp và chạy trong một ứng dụng do nhóm kiểm soát, đặc biệt khi cần thay đổi quy tắc mà không biên dịch lại toàn bộ ứng dụng.

### 3.2 Code generator — backend sinh mã

Code generator chuyển AST hoặc IR thành mã nguồn của một ngôn ngữ khác. Mã được sinh có thể tiếp tục được biên dịch hoặc chạy bởi công cụ tương ứng.

Ví dụ, DSL mô tả quy tắc kiểm tra hóa đơn có thể sinh lớp Java chứa các phép kiểm tra. Ứng dụng Java sau đó gọi lớp được sinh như một phần của quá trình xử lý hóa đơn.

Ưu điểm:

- Có thể tận dụng compiler, thư viện, công cụ gỡ lỗi và hệ sinh thái của target.
- Một phần chi phí diễn giải được chuyển sang giai đoạn sinh và biên dịch.
- Đầu ra có thể được lưu, kiểm tra hoặc triển khai độc lập.

Hạn chế:

- Phải quản lý mã nguồn được sinh, lỗi biên dịch và sự khác nhau giữa các phiên bản target.
- Debug có thể khó nếu không ánh xạ được dòng mã đích về vị trí trong DSL.
- Mã sinh cần tránh phụ thuộc không cần thiết vào cấu trúc nội bộ của generator.

### 3.3 Transpiler — backend chuyển đổi giữa các ngôn ngữ

Transpiler chuyển một ngôn ngữ nguồn hoặc biểu diễn trung gian sang một ngôn ngữ khác có mức trừu tượng tương đương. Trong thực tế, ranh giới giữa transpiler và code generator không phải lúc nào cũng tuyệt đối.

Ví dụ, một DSL biểu diễn biểu thức có thể được chuyển thành JavaScript để chạy trong trình duyệt hoặc thành Java để chạy trên máy chủ.

Transpiler cần giữ nguyên ý nghĩa của chương trình. Nếu ngôn ngữ đích có cách xử lý số, null, thời gian hoặc lỗi khác ngôn ngữ DSL, backend phải mô phỏng hoặc từ chối những cấu trúc không thể chuyển đổi an toàn.

### 3.4 Compiler backend — backend biên dịch sang mã máy hoặc bytecode

Một compiler backend có thể chuyển IR thành bytecode, mã máy hoặc một dạng mã thấp hơn. Cách này thường xuất hiện khi DSL cần hiệu năng cao, cần tối ưu hóa hoặc muốn chạy trên một runtime có sẵn.

Compiler backend thường phải xử lý thêm:

- Biểu diễn kiểu và quy tắc chuyển kiểu.
- Phân bổ thanh ghi hoặc bộ nhớ tùy target.
- Quy ước gọi hàm và bố trí dữ liệu.
- Tối ưu hóa biểu thức và luồng điều khiển.
- Metadata, debug information và liên kết thư viện runtime.

Đây là lựa chọn có chi phí triển khai cao hơn. Không nên xây dựng compiler backend phức tạp nếu interpreter hoặc code generator đã đáp ứng yêu cầu của DSL.

### 3.5 Backend sinh cấu hình hoặc dữ liệu

Không phải DSL nào cũng cần sinh chương trình thực thi. Một số DSL chỉ mô tả cấu hình, schema, kế hoạch hoặc tài liệu có cấu trúc.

Ví dụ:

- DSL mô tả biểu mẫu có thể sinh JSON Schema.
- DSL mô tả workflow có thể sinh cấu hình cho workflow engine.
- DSL mô tả hạ tầng có thể sinh manifest cho nền tảng triển khai.
- DSL mô tả báo cáo có thể sinh cấu hình truy vấn hoặc metadata cho công cụ báo cáo.

Backend dạng này cần đảm bảo đầu ra đúng schema, giữ được ý nghĩa các trường và có thể được target nạp mà không cần diễn giải thêm bằng mã tùy ý.

### 3.6 Backend sinh truy vấn

Một DSL có thể biểu diễn điều kiện tìm kiếm, lọc hoặc tổng hợp dữ liệu. Backend chuyển mô tả đó thành SQL hoặc ngôn ngữ truy vấn khác.

Ví dụ, biểu thức nghiệp vụ “hóa đơn có tổng tiền từ một triệu đồng trở lên và trạng thái đang mở” có thể được chuyển thành điều kiện truy vấn cơ sở dữ liệu.

Backend truy vấn cần đặc biệt chú ý đến:

- Tham số hóa giá trị để tránh SQL injection.
- Ánh xạ tên miền sang bảng, cột và quan hệ.
- Ngữ nghĩa null và phép so sánh.
- Phân trang, sắp xếp và giới hạn dữ liệu.
- Khả năng biểu diễn của target database.
- Quyền truy cập và phạm vi dữ liệu mà người dùng được phép xem.

Không nên nối chuỗi trực tiếp từ văn bản DSL thành SQL. Hãy tạo cây biểu thức có kiểu, kiểm tra nó rồi sinh truy vấn với tham số riêng.

## 4. Target có thể là gì?

Target không chỉ là một ngôn ngữ lập trình. Cần xác định target theo mục đích sử dụng thực tế.

| Nhóm target | Ví dụ | Kết quả backend tạo ra |
|---|---|---|
| Runtime ứng dụng | JVM, JavaScript runtime | Bytecode, mã nguồn hoặc cấu trúc thực thi |
| Ngôn ngữ lập trình | Java, Kotlin, JavaScript | Mã nguồn có thể biên dịch hoặc chạy |
| Cơ sở dữ liệu | PostgreSQL, Oracle, MySQL | SQL phù hợp với dialect của hệ quản trị |
| Rule engine | Engine đánh giá chính sách | Bộ quy tắc hoặc cấu hình tương ứng |
| Workflow engine | Nền tảng điều phối quy trình | Mô hình workflow hoặc file cấu hình |
| Định dạng dữ liệu | JSON, YAML, XML | Tài liệu có cấu trúc |
| Schema/validation | JSON Schema hoặc schema riêng | Định nghĩa cấu trúc và ràng buộc |
| Dịch vụ bên ngoài | API hoặc giao thức tích hợp | Request, payload hoặc lệnh gọi dịch vụ |

Một target cần được mô tả cụ thể hơn tên công nghệ. Ví dụ, “SQL” chưa đủ rõ vì PostgreSQL, Oracle và MySQL có cú pháp, kiểu dữ liệu, hàm và hành vi khác nhau. Tương tự, “Java” cần xác định phiên bản ngôn ngữ, phiên bản runtime và các thư viện mà mã sinh được phép sử dụng.

Khi chọn target, cần biết:

- Phiên bản và môi trường triển khai.
- Hệ kiểu và kiểu dữ liệu có sẵn.
- Cách biểu diễn lỗi và ngoại lệ.
- Cách truy cập dữ liệu hoặc tài nguyên.
- Khả năng đồng bộ, bất đồng bộ hoặc phân tán.
- Giới hạn bảo mật và quyền thực thi.
- Quy trình build, deploy và vận hành.

## 5. IR giúp tách ngôn ngữ khỏi backend như thế nào?

IR (Intermediate Representation — biểu diễn trung gian) là mô hình có cấu trúc dùng để diễn tả ý nghĩa đã được phân tích của chương trình DSL. IR thường ít phụ thuộc vào cách người dùng viết cú pháp và ít phụ thuộc vào một target cụ thể.

Ví dụ, người dùng viết:

~~~text
hoa_don tong_tien >= 1000000
va trang_thai == "MO"
~~~

Parser có thể tạo AST phản ánh các toán tử và tên thuộc tính. Sau khi phân tích ngữ nghĩa, hệ thống có thể tạo IR khái quát:

~~~text
AND
  GREATER_OR_EQUAL
    PROPERTY: invoice.total
    DECIMAL: 1000000
  EQUAL
    PROPERTY: invoice.status
    STRING: "MO"
~~~

IR này không quy định phải sinh Java hay SQL. Backend Java có thể tạo biểu thức Java; backend SQL có thể tạo điều kiện truy vấn. Cả hai cần hiểu invoice.total, invoice.status và các phép so sánh theo cùng một hợp đồng ngữ nghĩa.

### 5.1 AST và IR khác nhau ở đâu?

AST thường phản ánh cấu trúc cú pháp mà parser nhận được. IR có thể loại bỏ chi tiết cú pháp không còn cần thiết, chuẩn hóa biểu thức, bổ sung kiểu và thông tin phân tích.

| Đặc điểm | AST | IR |
|---|---|---|
| Mục đích | Biểu diễn cấu trúc nguồn | Biểu diễn ý nghĩa để xử lý tiếp |
| Phụ thuộc cú pháp | Thường cao hơn | Thường thấp hơn |
| Thông tin kiểu | Có thể chưa đầy đủ | Thường được bổ sung sau semantic analysis |
| Tối ưu hóa | Có thể thực hiện | Thường là nơi thuận tiện để chuẩn hóa và tối ưu |
| Nhiều backend | Có thể dùng trực tiếp với DSL nhỏ | Hữu ích khi cần nhiều target |

Không phải dự án nào cũng cần hai cấu trúc riêng. Nếu AST đã đủ ổn định và chứa đầy đủ thông tin ngữ nghĩa, có thể dùng nó như IR. Quan trọng là backend nhận một hợp đồng rõ ràng và không phải tự đoán ý nghĩa từ cú pháp.

### 5.2 IR cần giữ thông tin gì?

Tùy DSL, IR có thể chứa:

- Loại node và toán tử.
- Kiểu dữ liệu của biểu thức.
- Tên và định danh đã được phân giải.
- Phạm vi biến và tham chiếu.
- Thông tin vị trí nguồn để báo lỗi.
- Quy tắc hoặc metadata nghiệp vụ.
- Kiểu chuyển đổi đã được kiểm tra.
- Phiên bản ngữ nghĩa của DSL.

Không nên đưa mọi chi tiết của target vào IR chung. Nếu IR chứa quá nhiều chi tiết riêng của SQL hoặc JVM, các backend khác sẽ bị phụ thuộc vào một nền tảng. Khi một target thực sự cần thông tin riêng, có thể bổ sung metadata có phạm vi rõ ràng hoặc dùng một IR chuyên biệt sau giai đoạn IR chung.

## 6. Thiết kế hợp đồng giữa IR và backend

Backend cần nhận đầu vào và trả kết quả theo một giao diện ổn định. Hợp đồng này nên xác định:

1. Những loại node nào backend hỗ trợ.
2. Kiểu dữ liệu nào được hỗ trợ và cách chuyển đổi.
3. Cách xử lý node không hỗ trợ.
4. Cách tạo thông báo lỗi và cảnh báo.
5. Những phụ thuộc runtime mà đầu ra cần.
6. Cách ánh xạ vị trí trong DSL sang vị trí đầu ra.
7. Các tùy chọn cấu hình riêng của target.

Một giao diện khái niệm có thể như sau:

~~~java
interface DslBackend {
    TargetDescriptor target();

    BackendResult generate(
        ValidatedIr program,
        BackendOptions options
    );
}
~~~

Đây là ví dụ kiến trúc, không phải API bắt buộc của Java hay một thư viện cụ thể. ValidatedIr biểu thị chương trình đã được kiểm tra; BackendResult có thể chứa mã nguồn, cấu hình, metadata, cảnh báo và danh sách phụ thuộc cần thiết.

Nên phân biệt lỗi của các giai đoạn:

- **Lỗi cú pháp:** nguồn DSL không tuân theo grammar.
- **Lỗi ngữ nghĩa:** tên, kiểu hoặc quy tắc miền không hợp lệ.
- **Lỗi backend:** IR hợp lệ nhưng backend không hỗ trợ một cấu trúc hoặc tùy chọn.
- **Lỗi target/build:** đầu ra được sinh nhưng compiler, database hoặc runtime từ chối.
- **Lỗi thực thi:** chương trình hợp lệ nhưng dữ liệu hoặc môi trường khi chạy gây lỗi.

Thông báo lỗi cần chỉ ra giai đoạn và vị trí liên quan. Không nên báo tất cả thành “DSL không hợp lệ”, vì người dùng và người phát triển cần biết vấn đề nằm ở cú pháp, quy tắc miền hay khả năng của target.

## 7. Ví dụ: một DSL kiểm tra hóa đơn với nhiều target

Giả sử một tổ chức muốn mô tả các điều kiện kiểm tra hóa đơn bằng DSL. Một chính sách minh họa:

~~~text
invoice_policy "Hoa don hop le"
  require total >= 1000000
  require currency in ["VND", "USD"]
  require customer.status == "ACTIVE"
~~~

Đây là cú pháp giả định để minh họa kiến trúc. Trong dự án thật, nhóm phải xác định đơn vị tiền, thời điểm kiểm tra trạng thái khách hàng, ý nghĩa của tổng tiền và nguồn dữ liệu có thẩm quyền.

Sau khi parser và semantic analyzer xác nhận:

- total là giá trị tiền tệ.
- currency là mã tiền tệ.
- customer.status là thuộc tính có thể truy cập trong ngữ cảnh hóa đơn.
- Các toán tử được áp dụng trên kiểu dữ liệu tương thích.

Hệ thống tạo IR gồm ba điều kiện. Từ IR này, có thể xây dựng các backend khác nhau.

### 7.1 Target Java

Backend Java có thể sinh một lớp kiểm tra:

~~~java
public final class HoaDonHopLe {
    public boolean test(Invoice invoice) {
        return invoice.total().compareTo(
                   new BigDecimal("1000000")
               ) >= 0
            && Set.of("VND", "USD")
                   .contains(invoice.currency())
            && "ACTIVE".equals(
                   invoice.customer().status()
               );
    }
}
~~~

Mã minh họa sử dụng BigDecimal để tránh sai số nhị phân khi xử lý tiền. Một generator thực tế cần quyết định cách xử lý giá trị null, khách hàng thiếu, import, tên lớp, package, phiên bản Java và cách tạo thông báo lý do từng điều kiện không đạt.

### 7.2 Target JSON Schema

Backend JSON Schema có thể sinh một schema mô tả một phần cấu trúc và điều kiện:

~~~json
{
  "type": "object",
  "properties": {
    "total": {
      "type": "number",
      "minimum": 1000000
    },
    "currency": {
      "enum": ["VND", "USD"]
    },
    "customer": {
      "type": "object",
      "properties": {
        "status": {
          "const": "ACTIVE"
        }
      },
      "required": ["status"]
    }
  },
  "required": ["total", "currency", "customer"]
}
~~~

Schema có thể kiểm tra cấu trúc JSON và một số điều kiện. Tuy nhiên, việc xác định schema này có hoàn toàn tương đương với quy tắc nghiệp vụ hay không còn phụ thuộc vào cách biểu diễn tiền, số thập phân, giá trị thiếu và các ràng buộc liên trường. Backend phải công bố phần ngữ nghĩa được hỗ trợ và từ chối hoặc cảnh báo khi có cấu trúc không thể biểu diễn tương đương.

### 7.3 Target SQL

Backend SQL có thể sinh điều kiện lọc:

~~~sql
SELECT invoice_id, total, currency, customer_id
FROM invoice
WHERE total >= ?
  AND currency IN (?, ?)
  AND customer_status = ?;
~~~

Các dấu hỏi là tham số được bind riêng, không phải phần văn bản nối từ DSL. Trong hệ thống thực tế, customer_status có thể nằm ở bảng customer và cần JOIN. Backend cần biết ánh xạ miền sang schema dữ liệu, quyền truy cập, kiểu cột và dialect SQL.

### 7.4 Vì sao ba đầu ra không tự động tương đương?

Java có thể gọi một đối tượng customer trong bộ nhớ; JSON Schema kiểm tra một tài liệu; SQL đánh giá dữ liệu trong database. Ba môi trường có khác biệt về null, dữ liệu thiếu, kiểu số, quan hệ và thời điểm đọc dữ liệu.

Ví dụ, nếu customer không tồn tại:

- Java có thể ném NullPointerException nếu mã sinh không kiểm tra.
- JSON Schema có thể từ chối vì thiếu trường customer.
- SQL JOIN có thể loại bỏ bản ghi hoặc trả kết quả theo cách phụ thuộc vào loại JOIN.

Nếu DSL quy định “không có customer thì hóa đơn không hợp lệ”, mỗi backend phải tạo hành vi tương đương. Nếu không thể, backend cần báo rõ giới hạn thay vì âm thầm sinh đầu ra khác nghĩa.

## 8. Hỗ trợ nhiều target

Một DSL có thể cần chạy trên nhiều nền tảng vì ứng dụng máy chủ, trình duyệt, database hoặc công cụ vận hành có yêu cầu khác nhau.

Kiến trúc đa target thường có:

- Một frontend dùng chung để phân tích cú pháp.
- Một bộ phân tích ngữ nghĩa dùng chung để xác định ý nghĩa.
- Một IR chung mô tả phần ngữ nghĩa độc lập target.
- Nhiều backend riêng cho từng loại target.
- Bộ kiểm tra khả năng hỗ trợ để phát hiện cấu trúc không thể chuyển đổi.

Lợi ích:

- Người dùng chỉ học một ngôn ngữ.
- Các target dùng chung định nghĩa miền.
- Có thể bổ sung target mà không viết lại toàn bộ parser.
- Có thể kiểm tra tính nhất quán giữa các cách thực thi.

Chi phí và thách thức:

- Mỗi backend phải duy trì tương đương ngữ nghĩa.
- Target có khả năng khác nhau; không phải cấu trúc nào cũng chuyển đổi được.
- Phải kiểm thử trên từng phiên bản runtime hoặc nền tảng.
- Tài liệu cần nói rõ tính năng nào được hỗ trợ ở target nào.

### 8.1 Chọn chiến lược chung hay target-specific

Có hai hướng thiết kế:

**Hướng thứ nhất: IR chung với backend chuyên biệt.** Đây là lựa chọn phù hợp khi các target có thể biểu diễn cùng một tập con ngữ nghĩa. Mỗi backend chuyển cùng IR sang định dạng riêng.

**Hướng thứ hai: mô hình hoặc phần mở rộng riêng theo target.** Cách này cần thiết khi một target có năng lực đặc biệt hoặc yêu cầu metadata riêng. Tuy nhiên, phần mở rộng cần được đánh dấu rõ để không tạo cảm giác rằng mọi target đều hỗ trợ.

Không nên làm IR chung quá rộng chỉ để chứa mọi tính năng riêng lẻ. Một tập con ngữ nghĩa rõ ràng, có kiểm tra khả năng hỗ trợ, thường dễ duy trì hơn một mô hình chung với nhiều cờ tùy chọn không nhất quán.

### 8.2 Ma trận hỗ trợ tính năng

Có thể công bố một ma trận cho người dùng và người phát triển:

| Tính năng DSL | Java backend | JSON Schema backend | SQL backend |
|---|---|---|---|
| So sánh số | Có | Có, theo kiểu schema | Có, tùy kiểu cột |
| Kiểm tra tập giá trị | Có | Có | Có |
| Truy cập thuộc tính lồng nhau | Có, nếu model hỗ trợ | Có, theo cấu trúc JSON | Cần ánh xạ JOIN hoặc JSON |
| Gọi hàm tùy ý | Cần whitelist/runtime | Thường không hỗ trợ | Không hỗ trợ tùy ý |
| Truy cập dịch vụ ngoài | Cần runtime | Không phải mục tiêu của schema | Thường không phù hợp |
| Điều kiện phụ thuộc thời gian hiện tại | Cần quy định clock | Cần mở rộng hoặc giá trị đầu vào | Cần quy định hàm và timezone |

Bảng chỉ là ví dụ minh họa. Khả năng thực tế phụ thuộc vào DSL, backend, phiên bản target và hợp đồng ngữ nghĩa. Không được xem ô “Có” là cam kết tương đương nếu chưa có kiểm thử.

## 9. Ngữ nghĩa phải được giữ nhất quán giữa các target

Thách thức lớn nhất của kiến trúc đa backend là giữ nguyên ý nghĩa. Cùng một biểu thức DSL phải cho kết quả tương đương trong phạm vi mà các backend tuyên bố hỗ trợ.

Những điểm dễ khác nhau gồm:

### 9.1 Kiểu số và phép toán

Java có nhiều kiểu số; JavaScript dùng Number cho phần lớn phép tính thông thường; SQL phụ thuộc kiểu cột và hệ quản trị. Số nguyên, số thập phân, độ chính xác và làm tròn có thể khác nhau.

Với tiền tệ, cần định nghĩa rõ:

- Kiểu biểu diễn giá trị.
- Độ chính xác và scale.
- Quy tắc làm tròn.
- Đơn vị tiền và quy đổi.
- Phép so sánh giữa các đơn vị khác nhau.

Không nên để backend tự chọn kiểu số mặc định mà không có hợp đồng từ DSL.

### 9.2 Null, missing và giá trị không xác định

Một thuộc tính không có trong dữ liệu, có giá trị null hoặc không đọc được có thể mang ý nghĩa khác nhau. SQL dùng logic ba giá trị trong nhiều phép so sánh; JSON phân biệt thuộc tính vắng mặt với thuộc tính có giá trị null; Java có thể dùng null hoặc Optional.

DSL cần xác định rõ:

- Thuộc tính thiếu có phải lỗi không?
- Null có được so sánh không?
- Điều kiện không xác định được xem là false, lỗi hay trạng thái riêng?
- Các toán tử AND, OR và NOT xử lý trạng thái không xác định ra sao?

Backend phải triển khai đúng quy tắc đó hoặc báo không hỗ trợ.

### 9.3 Thời gian và múi giờ

Các target có thể dùng timezone mặc định khác nhau, độ chính xác timestamp khác nhau hoặc cách xử lý thời điểm chuyển giờ khác nhau.

Nếu DSL có điều kiện thời gian, cần xác định:

- Instant hay local date-time.
- Múi giờ dùng để đánh giá.
- Bao gồm hay không bao gồm thời điểm đầu và cuối.
- Độ chính xác và cách làm tròn.
- Clock lấy từ đâu và có thể cố định trong kiểm thử không.

### 9.4 Thứ tự đánh giá và tác dụng phụ

Một biểu thức có thể gọi hàm, truy cập dữ liệu hoặc gây tác dụng phụ. Nếu target thay đổi thứ tự đánh giá, kết quả hoặc tác động có thể khác.

DSL khai báo thường nên hạn chế tác dụng phụ trong biểu thức điều kiện. Nếu cho phép, cần quy định thứ tự đánh giá, số lần gọi và cách xử lý lỗi một cách tường minh.

### 9.5 Lỗi và kết quả

Một target có thể trả exception, target khác trả mã lỗi hoặc kết quả rỗng. DSL nên định nghĩa mô hình lỗi ở mức nghiệp vụ và yêu cầu backend ánh xạ theo cách có thể truy nguyên.

Ví dụ, “không đủ điều kiện” là một kết quả nghiệp vụ; “không kết nối được database” là lỗi hạ tầng. Không nên gộp hai loại này thành cùng một giá trị false.

## 10. Chọn backend và target phù hợp

Không có backend tốt nhất cho mọi DSL. Cần lựa chọn theo cách người dùng sử dụng mô tả, yêu cầu vận hành và năng lực của nhóm phát triển.

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Mục đích | DSL cần tính toán, điều khiển, cấu hình hay truy vấn? |
| Người dùng | Ai viết và ai vận hành mô tả? |
| Tần suất thay đổi | Quy tắc được cập nhật thường xuyên hay chỉ khi phát hành phần mềm? |
| Hiệu năng | Có yêu cầu độ trễ, thông lượng hoặc thời gian khởi động cụ thể không? |
| Môi trường | Chạy trong ứng dụng, browser, database hay nền tảng bên ngoài? |
| Tích hợp | Target có thư viện, API hoặc runtime phù hợp không? |
| Bảo mật | Mô tả có thể truy cập file, mạng, database hoặc gọi mã tùy ý không? |
| Khả năng kiểm thử | Có thể so sánh kết quả và kiểm tra tính tương đương không? |
| Khả năng bảo trì | Nhóm có thể nâng cấp target và duy trì generator không? |
| Khả năng quan sát | Có thể truy từ kết quả về dòng DSL và quy tắc nguồn không? |

Một số gợi ý:

- Chọn interpreter khi cần nạp và chạy quy tắc động trong một runtime do nhóm kiểm soát.
- Chọn code generator khi muốn tận dụng ngôn ngữ và công cụ có sẵn, hoặc cần đóng gói đầu ra.
- Chọn backend SQL khi bài toán thực sự là truy vấn dữ liệu và cần tận dụng database.
- Chọn backend sinh cấu hình khi target đã có engine thực thi phù hợp.
- Chỉ xây compiler backend chuyên sâu khi hiệu năng hoặc khả năng kiểm soát mã thấp hơn là yêu cầu đã được chứng minh.

Nên bắt đầu bằng một target có giá trị rõ ràng, xác nhận DSL giải quyết được công việc thật, rồi mới mở rộng. Hỗ trợ nhiều target từ đầu làm tăng đáng kể chi phí kiểm thử và duy trì.

## 11. Tổ chức backend trong mã nguồn

Một cách tổ chức phổ biến là tách phần dùng chung và phần target-specific:

~~~text
dsl/
  frontend/
    lexer/
    parser/
    ast/
    semantic/
  ir/
    model/
    validation/
  backend-api/
    DslBackend
    TargetDescriptor
    BackendResult
  backend-java/
    JavaBackend
    JavaEmitter
  backend-sql/
    SqlBackend
    SqlDialect
  backend-json-schema/
    JsonSchemaBackend
  runtime/
    diagnostics/
    source-mapping/
~~~

Đây là cách chia khái niệm; không bắt buộc mỗi thư mục phải là một module Gradle hoặc Maven riêng. Với dự án nhỏ, có thể giữ trong một module nhưng vẫn tách package và trách nhiệm.

Một số nguyên tắc:

- Frontend không phụ thuộc vào backend cụ thể.
- IR không nhập lớp của target nếu không cần thiết.
- Backend không tự phân tích lại văn bản nguồn.
- Mỗi backend khai báo rõ phiên bản và khả năng hỗ trợ.
- Phụ thuộc runtime được công bố cùng đầu ra.
- Lỗi và cảnh báo dùng một mô hình chung, có vị trí nguồn khi có thể.
- Không để một backend thay đổi ngữ nghĩa chung để phù hợp với giới hạn riêng của nó.

Nếu có cơ chế đăng ký backend, việc chọn backend nên dựa trên định danh target và cấu hình rõ ràng. Tránh tự chọn backend theo thứ tự nạp class hoặc tên file vì kết quả có thể không ổn định giữa môi trường.

## 12. Kiểm thử backend và target

Kiểm thử parser thành công không chứng minh backend đúng. Cần kiểm tra đầu ra và hành vi ở target.

### 12.1 Kiểm thử sinh mã hoặc cấu hình

Với một đầu vào IR cố định, so sánh đầu ra với kết quả mong đợi (golden file hoặc snapshot). Kiểm tra:

- Cú pháp đầu ra hợp lệ.
- Tên, kiểu và tham số được sinh đúng.
- Không sinh dữ liệu hoặc mã ngoài ý muốn.
- Thông tin vị trí nguồn được giữ nếu có hỗ trợ.
- Kết quả ổn định khi cùng đầu vào và cùng tùy chọn.

Snapshot hữu ích để phát hiện thay đổi không mong muốn, nhưng không đủ để chứng minh ngữ nghĩa. Mã nguồn có thể thay đổi hình thức mà vẫn tương đương, hoặc giống snapshot nhưng vẫn chạy sai.

### 12.2 Kiểm thử trên target thật

Biên dịch mã Java bằng phiên bản JDK đã cam kết; nạp JSON Schema bằng validator được hỗ trợ; chạy SQL trên database tương ứng. Kiểm tra cả trường hợp hợp lệ và không hợp lệ.

### 12.3 Kiểm thử tương đương giữa các backend

Với cùng một tập dữ liệu và cùng một chương trình DSL, chạy các backend và so sánh kết quả trong tập tính năng chung.

Ví dụ:

| Ca kiểm thử | Kết quả nghiệp vụ mong đợi |
|---|---|
| Tổng tiền thấp hơn ngưỡng | Không hợp lệ |
| Tổng tiền bằng ngưỡng | Hợp lệ nếu dùng lớn hơn hoặc bằng |
| Tiền tệ không được hỗ trợ | Không hợp lệ |
| Trạng thái khách hàng không hoạt động | Không hợp lệ |
| Thiếu khách hàng | Theo chính sách đã định nghĩa |

Nếu một target không thể biểu diễn một ca kiểm thử, phải đánh dấu rõ giới hạn hỗ trợ. Không bỏ qua ca đó rồi tuyên bố hai backend tương đương hoàn toàn.

### 12.4 Kiểm thử lỗi và khả năng chẩn đoán

Kiểm tra trường hợp backend gặp node không hỗ trợ, kiểu không hợp lệ, cấu hình target sai hoặc công cụ build thất bại. Thông báo cần cho biết:

- Loại lỗi và giai đoạn phát sinh.
- Vị trí DSL liên quan nếu có.
- Target và phiên bản đang dùng.
- Cách khắc phục hoặc tính năng thay thế nếu xác định được.

### 12.5 Kiểm thử bảo mật

Đặc biệt với backend sinh SQL, mã nguồn hoặc workflow:

- Không thực thi mã tùy ý chỉ vì văn bản DSL chứa tên hàm.
- Dùng whitelist cho hàm, thuộc tính và thao tác được phép.
- Bind tham số thay vì nối chuỗi truy vấn.
- Giới hạn tài nguyên, thời gian và số lần gọi.
- Kiểm soát quyền truy cập của runtime.
- Không để lỗi backend làm lộ bí mật hoặc dữ liệu ngoài phạm vi.

## 13. Source mapping, debug và vận hành

Khi backend sinh mã, lỗi ở target thường xuất hiện tại dòng mã được sinh chứ không phải dòng DSL mà người dùng đã viết. Source mapping giúp liên kết vị trí trong đầu ra với vị trí nguồn.

Ví dụ, nếu dòng thứ 12 của Java sinh ra từ điều kiện thứ 3 trong file DSL, thông báo lỗi có thể chỉ cả vị trí DSL lẫn vị trí mã Java. Điều này giúp người dùng sửa mô tả thay vì phải hiểu toàn bộ mã được sinh.

Đầu ra backend cũng nên có metadata:

- Phiên bản DSL và phiên bản backend.
- Target và phiên bản target.
- Hash hoặc định danh nguồn đầu vào.
- Thời điểm sinh.
- Phụ thuộc runtime và thư viện cần thiết.
- Cảnh báo về tính năng hoặc giới hạn.

Với backend chạy trực tiếp, cần có log hoặc trace để biết quy tắc nào được đánh giá, dữ liệu đầu vào thuộc phiên bản nào và vì sao kết quả được trả về. Chỉ ghi log những thông tin được phép; tránh lưu dữ liệu nhạy cảm không cần thiết.

## 14. Phiên bản DSL, backend và target

Ba thành phần có thể thay đổi độc lập:

- **Phiên bản DSL:** thay đổi grammar hoặc ngữ nghĩa của ngôn ngữ.
- **Phiên bản backend:** thay đổi cách chuyển IR hoặc sinh đầu ra.
- **Phiên bản target:** thay đổi runtime, compiler, database hoặc định dạng đích.

Một backend mới có thể hỗ trợ một phiên bản DSL nhưng không hỗ trợ phiên bản cũ. Một phiên bản database mới có thể thay đổi khả năng hoặc cú pháp mà backend sử dụng.

Nên ghi rõ ma trận tương thích:

| DSL | Backend | Target | Trạng thái |
|---|---|---|---|
| 1.x | Java backend 1.x | JDK phiên bản đã công bố | Hỗ trợ |
| 1.x | SQL backend 1.x | PostgreSQL phiên bản đã công bố | Hỗ trợ |
| 2.x | Java backend 1.x | JDK phiên bản đã công bố | Cần xác nhận |

Bảng trên chỉ minh họa cách ghi nhận tương thích. Dự án cần điền phiên bản thực tế, chính sách hỗ trợ và thời hạn ngừng hỗ trợ.

Khi ngữ nghĩa DSL thay đổi, cần cân nhắc migration, cảnh báo deprecation và khả năng chạy lại các ví dụ đã xác nhận. Không nên âm thầm thay đổi cách diễn giải một chính sách đã được triển khai.

## 15. Những sai lầm thường gặp

### Đồng nhất backend với target

Backend là thành phần xử lý; target là môi trường hoặc định dạng đích. Nếu dùng lẫn hai khái niệm, trách nhiệm sinh mã, thực thi và cấu hình dễ bị nhập nhằng.

**Cách xử lý:** mô tả riêng backend, target và hợp đồng đầu ra.

### Thiết kế DSL chỉ cho một công nghệ quá sớm

Nếu cú pháp chứa trực tiếp tên bảng, class hoặc API của target, ngôn ngữ có thể trở thành lớp vỏ cho công nghệ đó và khó chuyển môi trường.

**Cách xử lý:** giữ khái niệm nghiệp vụ trong frontend và IR; đặt ánh xạ kỹ thuật trong backend khi có thể.

### Cho rằng cùng một cú pháp luôn có cùng hành vi

Các target có thể xử lý null, số, thời gian và lỗi khác nhau.

**Cách xử lý:** định nghĩa ngữ nghĩa ở cấp DSL, viết kiểm thử tương đương và công bố giới hạn.

### Cố hỗ trợ mọi target

Một số cấu trúc không thể biểu diễn trên target khác mà vẫn giữ nguyên ý nghĩa.

**Cách xử lý:** xác định tập tính năng chung, kiểm tra khả năng hỗ trợ trước khi sinh đầu ra và từ chối rõ ràng cấu trúc không tương thích.

### Backend tự xử lý cú pháp và quy tắc miền

Mỗi backend có thể đưa ra cách hiểu khác nhau, tạo lỗi khó phát hiện.

**Cách xử lý:** dùng một frontend và semantic analyzer chung; backend nhận AST hoặc IR đã kiểm tra.

### Chỉ kiểm tra file đầu ra

Một file Java hoặc JSON hợp lệ về cú pháp vẫn có thể thực hiện sai quy tắc.

**Cách xử lý:** chạy đầu ra trên target thật và kiểm tra kết quả bằng các ví dụ nghiệp vụ đã xác nhận.

## 16. Các quyết định thiết kế cần ghi lại

Trước khi triển khai backend, nên có một bản mô tả quyết định gồm:

| Quyết định | Nội dung cần làm rõ |
|---|---|
| Mục đích backend | Sinh mã, diễn giải, chuyển đổi, sinh truy vấn hay cấu hình |
| Target | Tên công nghệ, phiên bản và môi trường triển khai |
| Đầu vào | AST hay IR, trạng thái kiểm tra và metadata cần thiết |
| Tập tính năng | Node, kiểu và toán tử được hỗ trợ |
| Ngữ nghĩa | Null, số, thời gian, lỗi, thứ tự đánh giá |
| Đầu ra | File, bytecode, cấu hình, truy vấn hoặc kết quả chạy |
| Runtime | Thư viện và dịch vụ cần có khi chạy |
| Giới hạn | Cấu trúc không hỗ trợ và cách báo lỗi |
| Bảo mật | Quyền, sandbox, giới hạn tài nguyên và dữ liệu |
| Kiểm thử | Golden test, target integration và equivalence test |
| Phiên bản | Tương thích DSL, backend và target |
| Vận hành | Logging, source mapping, triển khai và rollback |

Các quyết định này giúp nhóm đánh giá được chi phí duy trì trước khi cam kết hỗ trợ thêm target. Chúng cũng giúp người dùng biết một mô tả DSL có thể chạy ở đâu và những tính năng nào có hiệu lực trong môi trường đó.

## 17. Câu hỏi tự kiểm tra

1. Phân biệt backend và target trong kiến trúc DSL.
2. Backend nằm ở giai đoạn nào trong pipeline từ nguồn DSL đến chương trình thực thi?
3. Nêu điểm khác nhau giữa interpreter, code generator và transpiler.
4. Vì sao một DSL có nhiều target thường cần IR?
5. Backend SQL cần xử lý những rủi ro và khác biệt nào?
6. Vì sao cùng một biểu thức có thể cho kết quả khác nhau trên Java, JSON Schema và SQL?
7. Cần làm gì khi một backend không hỗ trợ một node trong IR?
8. Những loại kiểm thử nào cần có để xác nhận backend?
9. Phiên bản DSL, backend và target ảnh hưởng lẫn nhau như thế nào?
10. Khi nào nên bắt đầu với interpreter hoặc một target duy nhất thay vì xây dựng compiler đa target?

Khi thiết kế một DSL cụ thể, hãy bắt đầu từ cách người dùng cần sử dụng mô tả, xác định môi trường thực thi và lựa chọn backend phù hợp. Sau đó, viết rõ hợp đồng ngữ nghĩa và kiểm chứng đầu ra trên target thật. Một backend tốt phải biến mô tả DSL thành kết quả có thể dự đoán, kiểm tra và vận hành được.
