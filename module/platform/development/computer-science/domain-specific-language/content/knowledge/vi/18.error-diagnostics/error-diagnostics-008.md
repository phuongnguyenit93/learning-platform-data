# Khôi phục để báo nhiều lỗi

Khi phân tích cú pháp một chương trình DSL, parser có thể gặp đầu vào không tuân theo grammar: thiếu dấu `}`, thiếu giá trị sau `=`, dùng dấu phân cách sai hoặc đặt một khai báo ở vị trí không hợp lệ. Cách đơn giản nhất là dừng ngay tại lỗi đầu tiên. Tuy nhiên, người viết khi đó phải sửa từng lỗi rồi chạy lại công cụ nhiều lần. Với DSL được dùng trong IDE, tệp cấu hình hoặc quy trình build, trải nghiệm tốt hơn thường là parser có thể **khôi phục sau lỗi để tiếp tục phân tích và báo nhiều lỗi trong một lượt**.

Khôi phục lỗi cú pháp (syntax error recovery) là cơ chế giúp parser bỏ qua hoặc sửa tạm thời một phần đầu vào không hợp lệ, đưa trạng thái phân tích trở lại một điểm có thể tiếp tục. Mục tiêu là tìm thêm lỗi độc lập ở phía sau, đồng thời giữ cấu trúc của những phần vẫn phân tích được. Việc khôi phục chỉ phục vụ chẩn đoán và xây dựng cây cú pháp một phần; parser không được coi phần đầu vào đã sửa tạm như chương trình hợp lệ để thực thi mà không có bước xác nhận.

## 1. Vì sao cần khôi phục lỗi?

Giả sử người dùng viết một tệp cấu hình:

```text
service "catalog" {
    replicas =
    port 8080
    image = "catalog:2.0"
}

service "billing" {
    replicas = 2
    port = 9090
```

Tài liệu có nhiều vấn đề: thiếu giá trị sau `replicas =`, thiếu dấu `=` trước `8080`, và thiếu dấu đóng khối cho service `billing`. Nếu parser dừng ở lỗi đầu tiên, người dùng chỉ nhìn thấy một thông báo, dù có thể sửa nhiều lỗi cùng lúc.

Khôi phục giúp parser:

- Báo lỗi đầu tiên tại đúng vị trí.
- Bỏ qua phần không thể phân tích hoặc tạo nút lỗi đại diện.
- Tìm điểm đồng bộ tiếp theo như dấu xuống dòng, dấu `}` hoặc từ khóa `service`.
- Tiếp tục phân tích các khai báo sau đó.
- Thu thập nhiều diagnostics trong cùng một lần chạy.

Khả năng này đặc biệt hữu ích cho IDE, nơi tài liệu thường chưa hoàn chỉnh khi người dùng đang gõ. Trong công cụ kiểm tra cấu hình hoặc build, nó cũng giảm số vòng lặp sửa lỗi.

## 2. Phân biệt phát hiện lỗi và khôi phục lỗi

Phát hiện lỗi (error detection) xác định rằng token hoặc cấu trúc hiện tại không hợp lệ theo grammar. Khôi phục lỗi (error recovery) quyết định parser sẽ làm gì tiếp theo để tiếp tục.

Ví dụ, grammar yêu cầu:

```ebnf
Property = IDENTIFIER, "=", Expression ;
```

Nhưng đầu vào là:

```text
port 8080
```

Parser phát hiện rằng sau `IDENTIFIER` cần token `=`, nhưng token kế tiếp là `INTEGER`. Sau đó, parser có thể:

- Báo lỗi và bỏ qua đến dấu xuống dòng.
- Giả định dấu `=` bị thiếu, chèn một token tổng hợp rồi thử phân tích `8080` như giá trị.
- Xóa token `8080` nếu nó được xem là token thừa, dù cách này có thể không giữ được ý định người viết.
- Tạo một nút `ErrorProperty` và tiếp tục tại thuộc tính kế tiếp.

Phát hiện lỗi là điều bắt buộc; khôi phục là chính sách phụ thuộc vào loại DSL, parser và trải nghiệm công cụ mong muốn. Một parser có thể dùng nhiều chiến lược khác nhau ở những vị trí khác nhau.

## 3. Fail-fast và multi-error parsing

### 3.1. Dừng ở lỗi đầu tiên

Parser fail-fast dừng ngay khi gặp lỗi cú pháp. Cách này có ưu điểm là đơn giản, trạng thái parser không phải xử lý thêm các nhánh khôi phục và thông báo lỗi thường phản ánh nguyên nhân trực tiếp.

Fail-fast phù hợp với một số tình huống như giao thức đầu vào cần bị từ chối ngay, parser nhỏ dùng trong nội bộ hoặc khi việc tiếp tục có nguy cơ tạo cách hiểu sai. Tuy nhiên, với tài liệu do con người chỉnh sửa, người dùng phải sửa từng lỗi qua nhiều lần chạy.

### 3.2. Tiếp tục sau lỗi

Multi-error parsing cố gắng thu thập nhiều lỗi trong một lượt. Parser không cần khôi phục mọi lỗi bằng cách đoán chính xác ý định người viết. Nó chỉ cần tìm một điểm an toàn để tiếp tục và giữ được các cấu trúc độc lập phía sau.

Ví dụ, nếu một thuộc tính trong khối `service` sai cú pháp, parser có thể bỏ qua đến dấu xuống dòng hoặc dấu `}` tiếp theo rồi tiếp tục với thuộc tính kế tiếp. Nếu một khối đóng không đúng, parser có thể đồng bộ tại từ khóa mở đầu khai báo cấp cao tiếp theo.

### 3.3. Kết quả phân tích một phần

Sau khi khôi phục, parser có thể trả về:

- AST chứa các nút hợp lệ.
- Nút lỗi hoặc placeholder tại vùng không phân tích được.
- Danh sách diagnostics.
- Trạng thái cho biết tài liệu có lỗi và không thể thực thi.

Việc có AST không đồng nghĩa chương trình hợp lệ. Runtime hoặc code generator cần yêu cầu mô hình đã vượt qua các bước xác thực cần thiết.

## 4. Panic-mode recovery

Panic-mode recovery là chiến lược phổ biến: khi gặp lỗi, parser bỏ qua token cho đến khi gặp một token đồng bộ (synchronization token) mà nó có thể tiếp tục phân tích an toàn.

Ví dụ, trong DSL dùng dấu chấm phẩy để kết thúc câu lệnh, tập token đồng bộ có thể là:

```text
;  }  EOF
```

Trong DSL khai báo, các điểm đồng bộ có thể gồm:

```text
service  workflow  rule  module  }
```

Parser bỏ qua token cho đến một trong những điểm đó, rồi chuyển quyền điều khiển về quy tắc grammar phù hợp.

### 4.1. Tập token đồng bộ

Tập đồng bộ cần được chọn theo ngữ cảnh. Một dấu `}` có thể kết thúc khối hiện tại; từ khóa `service` có thể bắt đầu khai báo cấp cao mới. Nếu parser ở trong danh sách tham số, dấu `,` hoặc `)` có thể là điểm đồng bộ phù hợp.

Ví dụ:

| Ngữ cảnh lỗi | Token đồng bộ có thể dùng | Lý do |
|---|---|---|
| Thuộc tính trong khối | newline, `;`, `}` | Kết thúc thuộc tính hoặc khối |
| Danh sách tham số | `,`, `)`, `}` | Tìm ranh giới phần tử hoặc lời gọi |
| Khai báo cấp cao | từ khóa mở đầu khai báo, EOF | Bắt đầu cấu trúc độc lập tiếp theo |
| Biểu thức điều kiện | `then`, `)`, `{`, `;` | Quay lại ranh giới biểu thức/câu lệnh |
| Tài liệu hoàn chỉnh | EOF | Điểm kết thúc chắc chắn |

Nếu tập đồng bộ quá nhỏ, parser có thể bỏ qua nhiều phần hợp lệ. Nếu quá rộng, parser có thể dừng ở một token chưa đủ để khôi phục đúng ngữ cảnh. Vì vậy, nên xác định tập đồng bộ riêng cho từng quy tắc grammar quan trọng.

### 4.2. Ví dụ panic mode trong khối thuộc tính

Giả sử parser đang đọc:

```text
service "catalog" {
    replicas = 3
    port 8080
    image = "catalog:2.0"
    enabled = true
}
```

Sau khi phát hiện thiếu `=`, parser có thể bỏ qua phần `port 8080` đến newline tiếp theo. Sau đó, nó tiếp tục ở `image` và `enabled`, giữ lại các thuộc tính hợp lệ.

Nếu DSL cho phép biểu thức nhiều dòng, newline không phải lúc nào cũng là điểm đồng bộ an toàn. Khi đó, parser có thể dùng `;`, dấu đóng khối hoặc token mở đầu thuộc tính tiếp theo, dựa trên grammar.

### 4.3. Đảm bảo parser có tiến triển

Một lỗi phổ biến trong recovery là parser quay lại đúng vị trí cũ mà không tiêu thụ token, rồi gặp lại cùng lỗi vô hạn. Mọi nhánh recovery cần bảo đảm một trong các điều sau:

- Tiêu thụ ít nhất một token.
- Chuyển sang một quy tắc khác có thể xử lý token hiện tại.
- Kết thúc phân tích tại EOF.
- Đánh dấu trạng thái lỗi và trả quyền điều khiển cho caller có điểm đồng bộ rõ ràng.

Quy tắc tiến triển (progress guarantee) giúp parser không lặp vô hạn khi đầu vào sai.

## 5. FIRST, FOLLOW và điểm đồng bộ

Trong lý thuyết grammar, FIRST và FOLLOW có thể hỗ trợ lựa chọn token đồng bộ.

- `FIRST(A)` là tập token có thể xuất hiện đầu tiên trong chuỗi được sinh từ ký hiệu `A`.
- `FOLLOW(A)` là tập token có thể xuất hiện ngay sau ký hiệu `A` trong một dẫn xuất hợp lệ.

Khi parser đang phân tích một cấu trúc `A` và gặp lỗi, token thuộc `FOLLOW(A)` có thể là điểm phù hợp để dừng bỏ qua, vì nó có khả năng đánh dấu nơi cấu trúc `A` kết thúc.

Ví dụ, nếu `Property` nằm trong `ServiceBody`, các token mở đầu thuộc tính tiếp theo có thể thuộc `FIRST(Property)`, còn `}` có thể thuộc `FOLLOW(Property)` vì nó kết thúc danh sách thuộc tính. Tập đồng bộ thực tế thường kết hợp token FOLLOW với token mở đầu cấu trúc cùng cấp.

Không nên dùng FIRST/FOLLOW một cách máy móc. Nếu grammar có nhiều lựa chọn hoặc parser hỗ trợ biểu thức phức tạp, cần xem xét ngữ cảnh gọi và trạng thái delimiter. Một token có thể là điểm đồng bộ tốt ở một quy tắc nhưng không an toàn ở quy tắc khác.

## 6. Phrase-level recovery

Phrase-level recovery cố gắng sửa cục bộ một lỗi nhỏ thay vì bỏ qua toàn bộ phần còn lại đến điểm đồng bộ xa hơn. Parser có thể giả định một thao tác đơn giản như chèn, xóa hoặc thay token.

Ba thao tác cơ bản:

- **Insertion:** giả định người viết quên một token bắt buộc, ví dụ chèn `=` hoặc `)`.
- **Deletion:** bỏ qua một token thừa, ví dụ dấu phẩy xuất hiện hai lần.
- **Substitution:** xem token hiện tại như một token khác nếu có một cách sửa cục bộ rõ ràng.

Ví dụ đầu vào:

```text
replicas 3
```

Nếu grammar yêu cầu `replicas = INTEGER`, parser có thể chèn token `=` tổng hợp trước `3`, sau đó phân tích phần còn lại. Diagnostic vẫn phải báo rằng dấu `=` bị thiếu; token tổng hợp chỉ phục vụ khôi phục.

### 6.1. Chèn token tổng hợp

Một token tổng hợp (synthetic token) không xuất hiện trong văn bản nguồn nhưng được parser tạo tạm để tiếp tục. Nó nên được đánh dấu là synthetic và có span rỗng tại vị trí chèn.

Ví dụ:

```text
Token(type=EQUALS, synthetic=true, span=[offset, offset))
```

Điều này giúp AST vẫn có cấu trúc dự kiến, đồng thời diagnostics và formatter biết token đó không có trong nguồn.

### 6.2. Xóa token thừa

Nếu đầu vào là:

```text
replicas = = 3
```

Parser có thể bỏ token `=` thứ hai và tiếp tục phân tích `3`. Nhưng nếu token bị xóa thực ra là một phần của cấu trúc hợp lệ ở ngữ cảnh khác, việc sửa tự động có thể làm sai ý định. Phrase-level recovery nên dùng khi có một cách sửa đơn giản, ít gây bất ngờ.

### 6.3. Chọn sửa cục bộ

Một heuristic phổ biến là xem token hiện tại và token kế tiếp:

- Nếu token kế tiếp phù hợp với vị trí hiện tại, có thể xóa token hiện tại.
- Nếu token hiện tại phù hợp sau khi chèn một token bắt buộc, có thể chèn token đó.
- Nếu cả hai khả năng đều hợp lý, tránh đoán và chuyển sang panic mode.

Đây chỉ là heuristic. Parser cần ghi rõ diagnostic và không được âm thầm coi văn bản đã sửa là nguồn chuẩn.

## 7. Error productions

Error production là các luật grammar được thêm có chủ đích để nhận diện một số dạng lỗi thường gặp và cho phép parser tiếp tục.

Ví dụ grammar thông thường:

```ebnf
Property = IDENTIFIER, "=", Expression, ";" ;
```

Có thể thêm một nhánh lỗi để nhận diện trường hợp thiếu biểu thức:

```ebnf
Property = IDENTIFIER, "=", Expression, ";"
         | IDENTIFIER, "=", ERROR, ";" ;
```

Nhánh `ERROR` ở đây là ký hiệu giả định của parser hoặc công cụ sinh parser, không nhất thiết là token do lexer phát ra. Khi parser gặp `name = ;`, nó có thể tạo một thuộc tính lỗi, báo thiếu biểu thức và tiếp tục sau dấu `;`.

Error productions hữu ích khi một số lỗi phổ biến có dạng rõ ràng, chẳng hạn thiếu giá trị, thiếu dấu phân cách hoặc khai báo chưa hoàn chỉnh. Tuy nhiên, thêm quá nhiều nhánh lỗi làm grammar khó đọc và có thể tạo xung đột mới. Chỉ nên mô hình hóa các trường hợp có lợi ích chẩn đoán rõ.

## 8. Khôi phục trong parser recursive descent

Với recursive descent, mỗi hàm phân tích có thể nhận một tập token đồng bộ riêng. Khi một hàm không tìm thấy token mong đợi, nó phát diagnostic rồi bỏ qua token đến khi gặp điểm đồng bộ.

Ví dụ Java giản lược:

```java
void parseProperty() {
    if (!check(TokenType.IDENTIFIER)) {
        reportError("Expected property name", peek());
        synchronizeProperty();
        return;
    }

    Token name = advance();

    if (!match(TokenType.EQUALS)) {
        reportError("Expected '=' after property name", peek());
        synchronizeProperty();
        return;
    }

    Expression value = parseExpression();
    consume(TokenType.SEMICOLON, "Expected ';' after property");
    properties.add(new PropertyNode(name, value));
}

void synchronizeProperty() {
    while (!isAtEnd()) {
        if (previous().type() == TokenType.SEMICOLON) {
            return;
        }

        if (check(TokenType.RIGHT_BRACE)) {
            return;
        }

        if (check(TokenType.IDENTIFIER) && looksLikePropertyStart()) {
            return;
        }

        advance();
    }
}
```

Đây là ví dụ minh họa, không phải parser hoàn chỉnh. `looksLikePropertyStart()` cần dựa trên grammar thực tế để tránh xem một identifier bên trong biểu thức là thuộc tính mới. Hàm đồng bộ phải được thiết kế theo ngữ cảnh và cần bảo đảm caller biết token hiện tại đã được tiêu thụ hay chưa.

### 8.1. Ai chịu trách nhiệm tiêu thụ token đồng bộ?

Một lỗi dễ gây lặp là cả hàm recovery và caller đều không tiêu thụ token đang đứng ở điểm đồng bộ. Một quy ước phổ biến:

- Hàm `synchronize` dừng trước token đồng bộ và không tiêu thụ nó.
- Caller tiếp tục parse token đó như phần tử tiếp theo.

Hoặc:

- Hàm `synchronize` tiêu thụ token kết thúc như `;`.
- Caller bắt đầu từ token sau dấu kết thúc.

Cả hai cách đều dùng được nếu được thống nhất. Không nên để mỗi hàm parse tự chọn quy ước khác nhau.

## 9. Khôi phục trong parser LR

Parser LR thường dùng stack trạng thái và token lookahead. Một số công cụ sinh parser hỗ trợ token đặc biệt `error` trong grammar. Khi gặp lỗi, parser có thể:

1. Báo diagnostic tại token không hợp lệ.
2. Pop các trạng thái trên stack cho đến khi tìm được trạng thái có thể dịch chuyển token `error`.
3. Shift token lỗi vào stack.
4. Bỏ qua token đầu vào cho đến khi tìm được token mà parser có thể tiếp tục xử lý.
5. Tiếp tục phân tích theo grammar.

Cơ chế cụ thể phụ thuộc parser generator. Một số công cụ yêu cầu vài token liên tiếp được phân tích thành công trước khi phát sinh lỗi mới, nhằm tránh báo nhiều lỗi cho cùng một nguyên nhân.

Ví dụ grammar có thể dùng một quy tắc dạng:

```text
statement : error ';'
```

Quy tắc này cho phép parser bỏ qua phần sai cho đến dấu chấm phẩy, sau đó tiếp tục ở câu lệnh tiếp theo. Điểm đồng bộ phải phù hợp với cấu trúc DSL; nếu dùng `;` ở mọi nơi nhưng DSL không có dấu này, cần chọn token khác như `}` hoặc từ khóa mở đầu khai báo.

## 10. Theo dõi delimiter khi khôi phục

Các dấu mở và đóng như `(`, `)`, `[`, `]`, `{`, `}` tạo cấu trúc lồng nhau. Khi bỏ qua token, parser có thể gặp dấu `}` thuộc khối con hoặc khối cha. Nếu không theo dõi độ sâu, nó có thể đồng bộ quá sớm và làm mất cấu trúc phía sau.

Một chiến lược là duy trì stack delimiter hoặc bộ đếm độ sâu:

- Khi bỏ qua `(`, tăng độ sâu ngoặc tròn; khi gặp `)`, giảm độ sâu tương ứng.
- Tương tự cho `[` và `]`, `{` và `}`.
- Chỉ coi dấu kết thúc khối là điểm đồng bộ khi nó thuộc cấp độ phù hợp với ngữ cảnh recovery.

Ví dụ, khi đang khôi phục bên trong danh sách:

```text
values = [1, broken(2, 3, 4]
next = 10
```

Dấu `]` xuất hiện trong khi lời gọi `broken(` chưa đóng. Parser cần quyết định có chèn `)` trước `]` hay bỏ qua đến một điểm an toàn. Nếu chỉ dừng ở dấu `]` mà không hiểu trạng thái delimiter, cấu trúc phía sau có thể bị phân tích sai.

Không phải parser nào cũng cần một stack delimiter riêng; parser recursive descent có thể đã biểu diễn độ sâu qua call stack. Tuy nhiên, khi recovery bỏ qua token, cần bảo đảm trạng thái lồng nhau vẫn được xử lý nhất quán.

## 11. Hạn chế lỗi dây chuyền và diagnostics trùng lặp

Một lỗi cú pháp có thể làm parser mất đồng bộ. Khi đó, nhiều token phía sau bị hiểu sai và tạo ra hàng loạt diagnostics không phản ánh lỗi độc lập.

Ví dụ:

```text
service "catalog" {
    replicas =
    port = 8080
}
```

Nếu parser không nhận ra biểu thức `replicas` bị thiếu và tiếp tục xem `port` là một phần của biểu thức, nó có thể báo lỗi ở `port`, `=`, `8080` và `}`. Nhưng nguyên nhân gốc chỉ là thiếu giá trị sau `replicas =`.

Một số kỹ thuật giảm lỗi dây chuyền:

- Đồng bộ ở ranh giới cấu trúc đáng tin cậy.
- Sau một lỗi, yêu cầu parser tiêu thụ một số token hợp lệ trước khi báo lỗi mới.
- Giới hạn số diagnostics trong một vùng nguồn.
- Gộp các lỗi có cùng nguyên nhân hoặc cùng span.
- Phân biệt lỗi gốc với lỗi phát sinh từ recovery.
- Không phát nhiều diagnostics cho cùng một token chỉ vì nhiều quy tắc parser cùng thất bại.

### 11.1. Error distance

Một số parser dùng khái niệm error distance: sau khi phát một lỗi, parser cần phân tích thành công một số token trước khi cho phép phát lỗi tiếp theo. Ví dụ, chỉ phát lỗi mới sau ba token được tiêu thụ thành công.

Cách này giảm thông báo trùng lặp, nhưng có thể che mất một lỗi độc lập xuất hiện ngay sau lỗi trước. Vì vậy, error distance nên được điều chỉnh theo cấu trúc DSL và mức độ quan trọng của diagnostics.

### 11.2. Giới hạn số lỗi

Với tài liệu hỏng nặng, parser có thể tạo hàng nghìn lỗi và tiêu tốn nhiều thời gian hoặc bộ nhớ. Có thể giới hạn số diagnostics, ví dụ dừng sau 100 lỗi và hiển thị thông báo “đã đạt giới hạn số lỗi”. Giới hạn nên có thể cấu hình và không được làm parser tuyên bố tài liệu hợp lệ.

## 12. Nút lỗi trong AST và cây cú pháp một phần

Để giữ cấu trúc phía sau lỗi, AST có thể hỗ trợ nút lỗi (error node) hoặc nút thiếu (missing node).

Ví dụ:

```java
sealed interface Expression
    permits NumberLiteral, NameExpression, BinaryExpression, ErrorExpression {
}

record NumberLiteral(String text) implements Expression {}
record NameExpression(String name) implements Expression {}
record BinaryExpression(
    Expression left,
    TokenType operator,
    Expression right
) implements Expression {}
record ErrorExpression(SourceSpan span, String message) implements Expression {}
```

Nếu biểu thức thiếu sau dấu `=`, parser có thể tạo `ErrorExpression` tại vị trí tương ứng. Phần AST còn lại vẫn có thể chứa những thuộc tính và khai báo hợp lệ.

Nút lỗi nên mang thông tin đủ để IDE hiển thị vùng lỗi và tránh các bước sau gây lỗi thứ cấp. Type checker có thể coi kiểu của `ErrorExpression` là kiểu lỗi đặc biệt để ngừng lan truyền diagnostics không hữu ích. Code generator và runtime cần từ chối mô hình còn nút lỗi.

### 12.1. Missing token và error token

Có thể phân biệt:

- **Missing node/token:** parser giả định một thành phần bắt buộc bị thiếu và tạo placeholder ở vị trí rỗng.
- **Error node/token:** parser gặp một vùng đầu vào không thể diễn giải và giữ lại vùng đó như một lỗi.

Ví dụ, thiếu `)` có thể tạo `MissingToken(RIGHT_PAREN)`; một chuỗi token không hợp lệ giữa hai dấu phân cách có thể tạo `ErrorNode` bao phủ toàn vùng bị bỏ qua.

Giữ span chính xác giúp formatter hoặc quick fix đề xuất chèn token ở đúng vị trí mà không làm thay đổi nội dung khác.

## 13. Khôi phục lỗi từ lexer

Lexer cũng có thể gặp lỗi như chuỗi chưa đóng, escape không hợp lệ hoặc ký tự không được phép. Nếu lexer dừng ngay, parser không thể báo thêm lỗi ở phần sau.

Lexer có thể phát token lỗi hoặc diagnostic rồi tiếp tục tìm ranh giới an toàn. Ví dụ:

```text
message = "unterminated
port = 8080
```

Nếu grammar không cho phép chuỗi nhiều dòng, lexer có thể báo chuỗi chưa đóng tại cuối dòng và tiếp tục ở dòng kế tiếp. Tuy nhiên, nếu DSL cho phép chuỗi nhiều dòng, newline không phải điểm khôi phục an toàn; lexer phải tìm dấu nháy đóng hoặc EOF theo quy tắc string literal.

Token lỗi nên chứa loại lỗi và source span. Parser cần biết token đó đại diện cho vùng sai đã được lexer xử lý để không phát thêm một lỗi cú pháp chung cho cùng nguyên nhân.

## 14. Khôi phục trong tài liệu chưa hoàn chỉnh của IDE

Khi người dùng đang gõ, những trạng thái như thiếu dấu `}`, thiếu dấu nháy hoặc biểu thức chưa hoàn tất là bình thường. Parser cho IDE cần chịu được tài liệu tạm thời không hợp lệ và vẫn cung cấp thông tin hữu ích.

Ví dụ người dùng đang nhập:

```text
workflow "release" {
    task "compile" {
        retries =
```

Parser có thể tạo cây một phần:

```text
Workflow
  name: "release"
  Task
    name: "compile"
    retries: ErrorExpression / MissingExpression
```

Nó có thể tiếp tục hiển thị cấu trúc đã nhận diện, gợi ý kiểu giá trị phù hợp và đánh dấu vị trí thiếu biểu thức. Khi người dùng gõ tiếp, parser cập nhật cây và diagnostics.

Một IDE có thể dùng parser gia tăng, nhưng recovery vẫn cần bảo đảm kết quả thuộc revision hiện tại. Diagnostics từ một phiên bản văn bản cũ không nên xuất hiện sau khi người dùng đã sửa lỗi.

## 15. Diagnostic tốt khi có nhiều lỗi

Một diagnostic nên chứa dữ liệu có cấu trúc thay vì chỉ là chuỗi thông báo. Các trường thường hữu ích:

- Mã lỗi ổn định, ví dụ `DSL-PARSE-EXPECTED-EQUALS`.
- Mức độ: error, warning hoặc information.
- Thông điệp giải thích.
- Source ID và span chính.
- Token hoặc cấu trúc mong đợi.
- Vị trí liên quan, nếu có.
- Gợi ý sửa (quick fix) nếu có thể xác định an toàn.
- Nhãn cho biết lỗi được phát hiện trực tiếp hay phát sinh trong recovery.

Ví dụ đầu ra:

```text
config.dsl:3:10: error DSL-PARSE-EXPECTED-EQUALS
Expected '=' after property name 'port'.
    port 8080
         ^^^^

config.dsl:8:1: error DSL-PARSE-EXPECTED-RIGHT-BRACE
Expected '}' to close service 'billing'.
```

Các diagnostics nên được sắp xếp theo vị trí nguồn, nhưng thứ tự phát hiện nội bộ có thể khác. Nếu nhiều parser hoặc module chạy song song, lớp tổng hợp cần sắp xếp kết quả ổn định để người dùng không thấy danh sách lỗi thay đổi ngẫu nhiên giữa các lần chạy.

## 16. Ví dụ tổng hợp: khôi phục trong DSL cấu hình

Xét đầu vào:

```text
service "catalog" {
    replicas =
    port 8080
    image = "catalog:2.0"
}

service "billing" {
    replicas = 2
    port = 9090
```

Một parser có thể thực hiện như sau:

1. Đọc `service "catalog" {` và tạo nút service.
2. Gặp `replicas =` rồi thấy `port`, phát lỗi thiếu biểu thức.
3. Khôi phục đến đầu thuộc tính tiếp theo, tạo `ErrorProperty` cho `replicas`.
4. Gặp `port 8080`, phát lỗi thiếu `=`. Có thể chèn token `=` tổng hợp nếu grammar cho phép sửa cục bộ; nếu không, bỏ qua đến newline.
5. Phân tích `image = "catalog:2.0"` bình thường.
6. Đóng service `catalog` tại `}`.
7. Phân tích service `billing` và các thuộc tính hợp lệ.
8. Đến EOF khi vẫn còn khối `billing` mở, phát lỗi thiếu `}` tại EOF và tạo missing token.

AST kết quả có thể giữ hai service, các thuộc tính hợp lệ và nút lỗi tại những vùng sai. Danh sách diagnostics chứa các lỗi độc lập. Hệ thống vẫn đánh dấu tài liệu không hợp lệ và không thực thi cấu hình cho đến khi người dùng sửa xong.

## 17. Cách thiết kế điểm đồng bộ cho DSL

Điểm đồng bộ tốt thường nằm ở ranh giới cấu trúc có thể nhận diện rõ. Khi thiết kế DSL, nên xem xét:

- Mỗi câu lệnh có dấu kết thúc rõ hay không.
- Khối có token đóng riêng hay chỉ dựa vào thụt lề.
- Các khai báo cấp cao có từ khóa mở đầu riêng hay không.
- Danh sách có dấu phân cách và dấu đóng rõ ràng không.
- Biểu thức có token kết thúc hoặc delimiter để parser biết điểm dừng không.
- Các cấu trúc lồng nhau có thể khôi phục bằng độ sâu delimiter hay không.

Ví dụ, DSL dùng `;` kết thúc mọi câu lệnh thường dễ đồng bộ hơn DSL dựa hoàn toàn vào newline, nhất là khi biểu thức có thể kéo dài nhiều dòng. Ngược lại, DSL khai báo dùng dấu ngoặc nhọn và từ khóa rõ ràng cũng có thể khôi phục tốt tại `}` hoặc từ khóa mở đầu khai báo.

Không nhất thiết phải thêm dấu phân cách vào mọi DSL chỉ để recovery dễ hơn. Cần cân nhắc sự tự nhiên của cú pháp và mức độ người dùng mong đợi. Tuy nhiên, những ranh giới rõ ràng thường có lợi cho parser, formatter và thông báo lỗi.

## 18. Những sai lầm thường gặp

- **Bỏ qua quá ít token:** parser gặp lại cùng lỗi và lặp vô hạn.
- **Bỏ qua quá nhiều token:** một lỗi cục bộ làm mất nhiều khai báo hợp lệ phía sau.
- **Dùng một tập đồng bộ cho mọi quy tắc:** điểm dừng không phù hợp với ngữ cảnh.
- **Không theo dõi delimiter:** dừng ở dấu đóng khối thuộc cấu trúc con hoặc cha sai cấp.
- **Chèn token mà không đánh dấu:** AST trông như hợp lệ và người dùng không biết parser đã sửa tạm.
- **Tiếp tục thực thi AST lỗi:** dữ liệu được phục hồi bị nhầm là chương trình hợp lệ.
- **Báo lỗi dây chuyền:** một lỗi gốc tạo ra nhiều diagnostics trùng lặp.
- **Không gắn span:** người dùng không biết lỗi nằm ở đâu.
- **Không giới hạn số lỗi:** tài liệu hỏng nặng tạo quá nhiều thông báo và tốn tài nguyên.
- **Không phân biệt lỗi lexer và parser:** cùng một lỗi được báo hai lần ở hai tầng.
- **Khôi phục không xác định:** cùng đầu vào nhưng kết quả khác nhau do trạng thái hoặc thứ tự duyệt không ổn định.

## 19. Quy trình triển khai multi-error recovery

Có thể xây dựng cơ chế khôi phục theo các bước:

1. **Xác định ranh giới cấu trúc:** liệt kê token mở đầu, kết thúc khối, dấu phân cách và EOF.
2. **Thiết kế tập đồng bộ theo quy tắc:** dùng token FOLLOW và token mở đầu cấu trúc cùng cấp làm cơ sở.
3. **Chọn chiến lược recovery:** panic mode, phrase-level, error productions hoặc kết hợp.
4. **Quy định quyền sở hữu token đồng bộ:** xác định recovery tiêu thụ hay giữ lại token dừng.
5. **Bảo đảm tiến triển:** mỗi lần recovery phải tiêu thụ token, chuyển trạng thái hoặc kết thúc.
6. **Tạo AST một phần:** dùng error node hoặc missing node để giữ cấu trúc.
7. **Kiểm soát diagnostics:** giới hạn lỗi trùng lặp, phân biệt lỗi gốc và lỗi phát sinh.
8. **Giữ vị trí nguồn:** mọi token tổng hợp và nút lỗi cần có span phù hợp.
9. **Chặn thực thi khi còn lỗi:** chỉ runtime hoặc backend nhận mô hình đã xác thực.
10. **Đồng bộ với IDE:** gắn diagnostics và AST với revision tài liệu hiện tại.

## 20. Nguyên tắc thiết kế

- **Ưu tiên khôi phục tại ranh giới an toàn:** giữ lại càng nhiều cấu trúc hợp lệ càng tốt.
- **Chọn điểm đồng bộ theo ngữ cảnh:** không dùng một quy tắc bỏ qua chung cho mọi vị trí.
- **Kết hợp FIRST/FOLLOW với delimiter:** dùng grammar và trạng thái lồng nhau để tìm điểm tiếp tục.
- **Dùng sửa cục bộ thận trọng:** chỉ chèn hoặc xóa token khi cách sửa đủ rõ.
- **Đánh dấu nội dung tổng hợp:** không che giấu việc parser đã phục hồi tạm thời.
- **Giữ AST một phần có kiểm soát:** error node giúp công cụ tiếp tục làm việc mà không giả vờ chương trình hợp lệ.
- **Ngăn lỗi dây chuyền:** phân biệt nguyên nhân gốc, dùng error distance hoặc giới hạn diagnostics khi phù hợp.
- **Bảo đảm tiến triển:** recovery không được lặp vô hạn ở cùng vị trí.
- **Bảo vệ runtime:** không thực thi mô hình còn lỗi cú pháp hoặc lỗi ngữ nghĩa.
- **Giữ kết quả xác định:** cùng đầu vào và cùng grammar phải cho cùng diagnostics và điểm đồng bộ.

Khôi phục để báo nhiều lỗi giúp người viết DSL nhận được phản hồi đầy đủ hơn trong một lần phân tích. Cơ chế này cần kết hợp điểm đồng bộ phù hợp, sửa cục bộ có kiểm soát, AST một phần và quản lý diagnostics để parser tiếp tục mà không làm sai cấu trúc phía sau. Khi mỗi nhánh recovery bảo đảm tiến triển, giữ vị trí nguồn và phân biệt rõ mô hình tạm thời với mô hình hợp lệ, DSL có thể cung cấp trải nghiệm sửa lỗi hiệu quả trong cả công cụ dòng lệnh lẫn IDE.
