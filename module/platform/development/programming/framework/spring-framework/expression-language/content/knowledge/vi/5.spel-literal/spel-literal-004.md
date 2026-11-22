# Literal số mũ và giá trị lớn trong Spring Expression Language

Spring Expression Language (SpEL) hỗ trợ literal số nguyên và số thực ngay trong biểu thức. Với số có giá trị lớn hoặc được viết theo ký pháp khoa học, cần hiểu cách SpEL phân loại literal, cách hậu tố xác định kiểu số và giới hạn độ chính xác của kiểu nền tảng Java. Một biểu thức có thể được phân tích thành công nhưng vẫn cho kết quả không phù hợp nếu chọn kiểu số quá nhỏ hoặc dùng floating point cho dữ liệu cần độ chính xác thập phân tuyệt đối.

## 1. Literal số trong SpEL

Literal là giá trị được viết trực tiếp trong chuỗi biểu thức. Các nhóm thường gặp:

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| Số nguyên | `42`, `-7` | Giá trị nguyên; dấu âm được áp dụng bằng toán tử một ngôi |
| Số nguyên kiểu long | `2147483648L` | Dùng hậu tố `L` hoặc `l` để chỉ định Long |
| Số thực thập phân | `12.5` | Literal số thực; mặc định là Double |
| Ký pháp khoa học | `1.25e3`, `4.2E-6` | Biểu diễn số thực bằng phần trị và số mũ |
| Số thực kiểu float | `1.25e3F` | Hậu tố `F` hoặc `f` chỉ định Float |
| Số thực kiểu double | `1.25e3D` | Hậu tố `D` hoặc `d` chỉ định Double |

SpEL sử dụng cú pháp số dựa trên các kiểu số của Java. Dấu thập phân trong biểu thức là dấu chấm, bất kể locale của máy chạy ứng dụng. Không dùng dấu phẩy để thay dấu chấm thập phân.

## 2. Ký pháp khoa học (scientific notation)

Ký pháp khoa học biểu diễn một số dưới dạng phần trị nhân với mười lũy thừa số mũ:

`a e n` tương đương `a × 10^n`

Trong SpEL, có thể dùng chữ `e` hoặc `E`. Số mũ có thể có dấu `+` hoặc `-`.

| Literal | Giá trị toán học | Diễn giải |
|---|---:|---|
| `1.25e3` | 1,250 | 1.25 × 10³ |
| `4.2E-3` | 0.0042 | 4.2 × 10⁻³ |
| `6.02e23` | 602,000,000,000,000,000,000,000 | 6.02 × 10²³ |
| `7e+8` | 700,000,000 | 7 × 10⁸ |
| `9.5e-7` | 0.00000095 | 9.5 × 10⁻⁷ |

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Object distance = parser.parseExpression("1.25e3").getValue();
    Object ratio = parser.parseExpression("4.2E-3").getValue();

Với literal thực không có hậu tố, SpEL mặc định dùng kiểu Double. Vì vậy `1.25e3` cho một giá trị Double tương đương 1250.0, dù kết quả toán học là số nguyên. Ký pháp khoa học vẫn biểu diễn một literal số thực; nó không tự biến giá trị thành Integer hoặc Long.

Dấu trong số mũ chỉ quyết định dịch chuyển dấu thập phân. Ví dụ `1e6` là một triệu, còn `1e-6` là một phần triệu. Dấu âm đứng trước toàn bộ biểu thức, như trong `-1.25e3`, được xử lý bởi toán tử trừ một ngôi.

Có thể kết hợp ký pháp khoa học với hậu tố kiểu số:

    Object asFloat = parser.parseExpression("1.25e3F").getValue();
    Object asDouble = parser.parseExpression("1.25e3D").getValue();

Hãy dùng hậu tố khi muốn kiểu dữ liệu được thể hiện rõ trong biểu thức hoặc khi cần truyền giá trị tới API có yêu cầu kiểu cụ thể.

## 3. Hậu tố và kiểu số

Hậu tố giúp chỉ định kiểu số mà literal đại diện:

| Hậu tố | Kiểu Java | Dùng cho |
|---|---|---|
| Không có hậu tố ở số nguyên | Integer theo quy tắc literal số nguyên của SpEL | Số nguyên trong miền kiểu phù hợp |
| `L` hoặc `l` | Long | Số nguyên cần miền 64 bit |
| Không có hậu tố ở số thực | Double | Số thực thông thường |
| `F` hoặc `f` | Float | Khi API hoặc cấu trúc dữ liệu yêu cầu Float |
| `D` hoặc `d` | Double | Khi muốn ghi rõ kiểu Double |

Ví dụ với số nguyên lớn hơn miền Integer:

    Object count = parser.parseExpression("2147483648L").getValue();

Hậu tố `L` cho biết literal cần được hiểu là Long. Với số nguyên lớn, hãy chỉ định kiểu đích một cách tường minh thay vì trông chờ vào chuyển đổi ngầm trong các phép toán hoặc khi truyền tham số.

Không nhầm hậu tố kiểu với số mũ. Trong `3.5e8F`, `e8` là phần số mũ và `F` là hậu tố chỉ kiểu Float.

## 4. Giới hạn khi xử lý giá trị lớn

Mỗi kiểu số có miền biểu diễn và độ chính xác riêng. Chọn kiểu phù hợp quan trọng hơn việc chỉ viết thêm nhiều chữ số vào literal.

| Kiểu | Đặc điểm | Lưu ý |
|---|---|---|
| Integer | Số nguyên có dấu 32 bit | Miền từ -2,147,483,648 đến 2,147,483,647 |
| Long | Số nguyên có dấu 64 bit | Miền từ -9,223,372,036,854,775,808 đến 9,223,372,036,854,775,807 |
| Float | Floating point 32 bit | Độ chính xác khoảng 6–7 chữ số thập phân có nghĩa |
| Double | Floating point 64 bit | Độ chính xác khoảng 15–17 chữ số thập phân có nghĩa |

### 4.1. Số nguyên vượt miền Integer

Nếu giá trị vượt miền Integer, hãy dùng Long với hậu tố `L`:

    2147483648L
    9000000000000L

Long vẫn có giới hạn. Nếu giá trị vượt miền Long, literal số nguyên thông thường không phải cách biểu diễn phù hợp. Có thể dùng BigInteger thông qua biến được truyền vào context hoặc tạo đối tượng nếu context cho phép constructor invocation.

### 4.2. Số thực rất lớn hoặc rất nhỏ

Double biểu diễn được dải giá trị rộng, nhưng có số chữ số có nghĩa hữu hạn. Khi số mũ quá lớn, giá trị có thể vượt miền hữu hạn và trở thành vô cực theo quy tắc floating point. Khi số mũ quá âm, giá trị có thể bị làm tròn xuống 0 hoặc mất một phần độ chính xác do underflow.

Ví dụ:

    1.0e300
    1.0e-300

Các biểu thức trên nằm trong dải biểu diễn hữu hạn của Double, nhưng điều đó không có nghĩa mọi giá trị có nhiều chữ số đều được lưu chính xác. Với Float, miền biểu diễn và độ chính xác còn nhỏ hơn.

### 4.3. Floating point không phù hợp cho mọi phép tính thập phân

Float và Double lưu số theo dạng nhị phân. Nhiều phân số thập phân, chẳng hạn 0.1, không có biểu diễn nhị phân hữu hạn. Vì vậy phép tính có thể cho kết quả gần đúng thay vì đúng tuyệt đối.

Ví dụ, không nên dùng Double làm kiểu lưu trữ tiền nếu nghiệp vụ yêu cầu phép cộng, trừ và so sánh chính xác đến từng chữ số thập phân. Tăng số chữ số trong literal hoặc đổi sang ký pháp khoa học không giải quyết được giới hạn này.

Với số nguyên lớn cần giữ từng chữ số, dùng `java.math.BigInteger`. Với số thập phân cần độ chính xác, dùng `java.math.BigDecimal`. Hai kiểu này có thể được đưa vào SpEL thông qua biến trong EvaluationContext hoặc tạo bằng constructor khi context cho phép.

## 5. Dùng BigInteger và BigDecimal trong biểu thức

StandardEvaluationContext cho phép dùng constructor invocation theo cấu hình mặc định. Có thể tạo BigInteger từ chuỗi số nguyên:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    ExpressionParser parser = new SpelExpressionParser();

    Object largeInteger = parser.parseExpression(
            "new java.math.BigInteger('123456789012345678901234567890')"
    ).getValue(context);

Với số thập phân cần giữ chính xác, tạo BigDecimal từ chuỗi thập phân:

    Object preciseDecimal = parser.parseExpression(
            "new java.math.BigDecimal('1234567890.12345678901234567890')"
    ).getValue(context);

Nên truyền chuỗi trực tiếp vào constructor BigDecimal. Nếu tạo BigDecimal từ một giá trị Double đã bị làm tròn trước đó, độ chính xác ban đầu đã mất và BigDecimal không thể khôi phục các chữ số đó.

Một cách khác là tạo giá trị ở Java rồi đưa vào context dưới dạng biến:

    BigDecimal amount =
            new BigDecimal("1234567890.12345678901234567890");

    context.setVariable("amount", amount);

    BigDecimal value = parser.parseExpression("#amount")
            .getValue(context, BigDecimal.class);

Cách truyền biến hữu ích khi dữ liệu đến từ database, API hoặc logic nghiệp vụ. Nó cũng giúp giới hạn quyền của biểu thức: ứng dụng quyết định giá trị nào được cung cấp cho context.

Lưu ý: SimpleEvaluationContext không hỗ trợ constructor invocation. Nếu dùng context giới hạn này, hãy tạo BigInteger hoặc BigDecimal ở Java rồi đưa vào bằng biến hoặc root object.

## 6. Đọc và kiểm tra kiểu kết quả

Khi kiểm tra literal, hãy quan sát cả giá trị lẫn kiểu runtime. Hai literal có cùng giá trị toán học vẫn có thể có kiểu khác nhau:

    Object a = parser.parseExpression("1.25e3").getValue();
    Object b = parser.parseExpression("1.25e3F").getValue();
    Object c = parser.parseExpression("1250L").getValue();

    System.out.println(a.getClass()); // Double
    System.out.println(b.getClass()); // Float
    System.out.println(c.getClass()); // Long

Khi gọi `getValue(..., DesiredType.class)`, SpEL có thể sử dụng cơ chế chuyển đổi kiểu của context để chuyển kết quả sang kiểu đích. Đây là chuyển đổi khi lấy kết quả; nó không làm cho literal ban đầu có độ chính xác cao hơn hoặc mở rộng miền biểu diễn của kiểu nguồn.

Nếu biểu thức được dùng làm tham số cho method, constructor hoặc property, hãy kiểm tra kiểu tham số đích và quy tắc chuyển đổi tương ứng. Đừng giả định rằng một literal Double luôn được truyền như một Long hoặc ngược lại mà không có chuyển đổi.

## 7. Lỗi thường gặp và cách tránh

- **Dùng dấu phẩy làm dấu thập phân:** SpEL dùng dấu chấm trong literal số. Viết `12.5`, không viết `12,5`.
- **Nhầm số mũ với hậu tố:** `e-4` là phần mũ; `F` hoặc `D` mới là hậu tố kiểu số thực.
- **Cho rằng `1e3` là số nguyên:** Đây là literal số thực và mặc định có kiểu Double.
- **Bỏ hậu tố Long ở số nguyên lớn:** Dùng `L` để thể hiện rõ ý định sử dụng Long.
- **Dùng Double cho dữ liệu cần chính xác thập phân:** Dùng BigDecimal, khởi tạo từ chuỗi hoặc từ dữ liệu chính xác.
- **Dùng Float cho giá trị cần nhiều chữ số có nghĩa:** Float chỉ có độ chính xác khoảng 6–7 chữ số; ưu tiên Double hoặc BigDecimal tùy yêu cầu.
- **Cho rằng BigDecimal sửa được dữ liệu Double đã sai lệch:** Hãy tạo BigDecimal từ chuỗi hoặc dữ liệu thập phân gốc.
- **Quên giới hạn của EvaluationContext:** SimpleEvaluationContext không cho phép tạo đối tượng bằng `new`; hãy chuẩn bị đối tượng trong Java và truyền qua biến.

## 8. Ghi nhớ

Ký pháp khoa học dùng `e` hoặc `E` để biểu diễn số mũ và rất hữu ích khi viết số rất lớn hoặc rất nhỏ. Literal thực không có hậu tố mặc định là Double; `F` chọn Float và `D` chọn Double. Với số nguyên lớn hơn miền Integer, dùng hậu tố `L` để chỉ định Long. Float và Double có giới hạn về miền biểu diễn và độ chính xác; khi cần số nguyên tùy ý hoặc thập phân chính xác, hãy dùng BigInteger hoặc BigDecimal và truyền giá trị vào EvaluationContext một cách có chủ đích.
