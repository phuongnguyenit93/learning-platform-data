# Tránh refactor khi domain chưa rõ: bảo toàn hành vi khi thay legacy cast bằng pattern matching

## 1. Bản chất vấn đề

**Refactor** là thay đổi cấu trúc mã nhưng **không làm thay đổi hành vi quan sát được** theo hợp đồng hiện tại. Trong Java, một thao tác trông rất hấp dẫn là đổi:

```java
if (value instanceof Customer) {
    Customer customer = (Customer) value;
    handle(customer);
}
```

thành:

```java
if (value instanceof Customer customer) {
    handle(customer);
}
```

Với cùng một đối tượng `value` và cùng luồng điều khiển, đây thường là **cải tiến cú pháp nhỏ, có thể bảo toàn hành vi**. Tuy nhiên, khi chưa hiểu rõ **domain** (các kiểu dữ liệu thật sự, trạng thái nghiệp vụ, thứ tự ưu tiên, ngoại lệ, chính sách đối với giá trị không biết, side effect...), đừng mặc nhiên suy ra rằng có thể tiếp tục biến cả chuỗi `if/else` thành `switch`, thêm `sealed`, thay cast bằng record patterns lồng nhau hoặc xóa các nhánh bị coi là “thừa”.

**Chủ đề này không phải “tránh sử dụng pattern matching”.** Mục tiêu là biết khi nào **dừng refactor để điều tra hợp đồng**. Một thay đổi đúng cú pháp Java chưa chắc đúng semantics của nghiệp vụ.

Ví dụ điển hình: class `UrgentText` là một loại `Text`, nhưng cần được xử lý **trước** các `Text` thông thường. Nếu gộp hai nhánh thành một pattern `Text text`, chương trình vẫn có thể biên dịch nhưng mất quy tắc ưu tiên của domain.

### Domain chưa rõ nghĩa là gì?

Có thể thiếu câu trả lời cho một hoặc nhiều câu hỏi:

- Hệ thống có những biến thể đối tượng nào? Có subclass, plugin, proxy, dữ liệu cũ hoặc kiểu chưa gặp trong test không?
- Nhánh nào được ưu tiên, và thứ tự đó có là một quy tắc nghiệp vụ không?
- `null`, kiểu không hỗ trợ, giá trị lỗi hoặc dữ liệu thiếu trường phải được xử lý ra sao?
- Mã cũ có chủ ý ném `ClassCastException`, `NullPointerException`, lỗi kiểm tra dữ liệu, hay trả về một giá trị dự phòng không?
- Những nhánh nào ghi log, đo metric, cache, gọi database, phát sự kiện hoặc thay đổi trạng thái?
- Có ràng buộc tương thích với API công khai, serialization, các module khác hay những phiên bản đã triển khai không?

**Nguyên tắc:** Nếu không giải thích được các nhánh bằng hợp đồng domain hoặc bài test đặc trưng, không nên gọi một lần “dọn dẹp” lớn là behavior-preserving refactor.

## 2. Phân biệt thay đổi cú pháp an toàn và thay đổi quy tắc nghiệp vụ

| Thao tác | Khi nào tương đối an toàn? | Rủi ro khi domain chưa rõ |
| --- | --- | --- |
| `instanceof Type` rồi cast **chính biến đó** thành `instanceof Type name` | Cùng đối tượng, cùng vị trí kiểm tra, cùng thân nhánh và fallback | Thay đổi biến nguồn, phạm vi biến hoặc biểu thức có side effect có thể làm khác hành vi |
| Giữ nguyên thứ tự các nhánh `if/else if` | Các điều kiện/ưu tiên cũ được giữ nguyên | Đổi thứ tự có thể thay đổi cách xử lý subclass |
| Gộp nhiều nhánh thành pattern kiểu cha | Đã chứng minh các subtype có cùng hợp đồng xử lý | Mất nhánh nghiệp vụ đặc biệt |
| Đổi `if` thành `switch` pattern | Đã nắm null, precedence, guards, side effects, fallback | Dominated case, thay đổi xử lý null hoặc thứ tự đánh giá |
| Thay cast/gọi getter bằng nested record pattern | Domain và hợp đồng accessor đã rõ | Thay thời điểm hoặc số lần truy cập component; null có thể khớp khác |
| Đổi interface/class thường thành `sealed` | Đã kiểm kê toàn bộ kiểu triển khai trực tiếp và tương thích module | Chặn subclass/plugin hợp lệ của hệ thống |
| Thay cast generic bằng pattern | Kiểu kiểm tra được tại runtime theo quy tắc Java | Type erasure; việc “xác nhận” `List<String>` có thể không hợp lệ |
| Xóa fallback “không bao giờ xảy ra” | Có hợp đồng, telemetry và test chứng minh | Mất khả năng tiếp nhận dữ liệu mới/cũ; đổi exception hoặc response |

**Đường ranh:** Một thay đổi máy móc giúp mã dễ đọc mà vẫn giữ mọi nhánh thường ít rủi ro hơn việc “chuẩn hóa mô hình” dựa trên giả định. Đừng trộn hai mục tiêu này vào cùng một pull request khi domain chưa rõ.

## 3. Ví dụ hoàn chỉnh: bản refactor an toàn và bản làm mất nghiệp vụ

Giả sử một hệ thống tiếp nhận nhiều loại message. Chưa có tài liệu nào đảm bảo toàn bộ kiểu message đã biết, và `UrgentText` là subclass của `Text`.

Lưu chương trình thành **`LegacyCastRefactorDemo.java`**. Ví dụ chạy được với **Java 17+** vì pattern matching cho `instanceof` chính thức từ Java 16 (JEP 394); không dùng preview.

```java
public class LegacyCastRefactorDemo {
    interface Message {}

    static class Text implements Message {
        private final String value;

        Text(String value) {
            this.value = value;
        }

        String value() {
            return value;
        }
    }

    static final class UrgentText extends Text {
        UrgentText(String value) {
            super(value);
        }
    }

    static final class Count implements Message {
        private final int value;

        Count(int value) {
            this.value = value;
        }

        int value() {
            return value;
        }
    }

    static final class Unknown implements Message {}

    // Mã cũ: kiểm tra kiểu trước, rồi cast thủ công.
    static String legacy(Message message) {
        if (message instanceof UrgentText) {
            UrgentText urgent = (UrgentText) message;
            return "urgent:" + urgent.value();
        }
        if (message instanceof Text) {
            Text text = (Text) message;
            return "text:" + text.value();
        }
        if (message instanceof Count) {
            Count count = (Count) message;
            return "count:" + count.value();
        }
        return "unsupported";
    }

    // Refactor nhỏ: chỉ thay instanceof + cast.
    // Giữ thứ tự, quy tắc nhánh và fallback như ban đầu.
    static String safe(Message message) {
        if (message instanceof UrgentText urgent) {
            return "urgent:" + urgent.value();
        }
        if (message instanceof Text text) {
            return "text:" + text.value();
        }
        if (message instanceof Count count) {
            return "count:" + count.value();
        }
        return "unsupported";
    }

    // Refactor vội: vô tình xóa quy tắc ưu tiên UrgentText.
    // Chương trình vẫn biên dịch nhưng cho kết quả khác.
    static String premature(Message message) {
        if (message instanceof Text text) {
            return "text:" + text.value();
        }
        if (message instanceof Count count) {
            return "count:" + count.value();
        }
        return "unsupported";
    }

    static void compare(String label, Message input) {
        System.out.println(label + " -> legacy=" + legacy(input)
                + " | safe=" + safe(input)
                + " | premature=" + premature(input));
    }

    public static void main(String[] args) {
        compare("ordinary", new Text("hello"));
        compare("urgent", new UrgentText("alert"));
        compare("count", new Count(3));
        compare("unknown", new Unknown());
        compare("null", null);
    }
}
```

Biên dịch, chạy bằng JDK 17 trở lên:

```bash
javac --release 17 LegacyCastRefactorDemo.java
java LegacyCastRefactorDemo
```

Stdout:

```text
ordinary -> legacy=text:hello | safe=text:hello | premature=text:hello
urgent -> legacy=urgent:alert | safe=urgent:alert | premature=text:alert
count -> legacy=count:3 | safe=count:3 | premature=count:3
unknown -> legacy=unsupported | safe=unsupported | premature=unsupported
null -> legacy=unsupported | safe=unsupported | premature=unsupported
```

### Điều gì bị thay đổi?

- `legacy` và `safe` đều xét `UrgentText` **trước** `Text`. Một `UrgentText` cũng là `Text`, nhưng nhánh đặc thù được chọn đúng như quy tắc cũ.
- `premature` không còn nhánh ưu tiên `UrgentText`. Vì `UrgentText extends Text`, điều kiện `instanceof Text` vẫn đúng. Kết quả `urgent:alert` biến thành `text:alert`.
- Với `Unknown` và `null`, tất cả phiên bản còn trả về `unsupported` nhờ fallback. Nếu xóa fallback và tự ném ngoại lệ, hành vi cũng sẽ đổi.
- **Compiler không thể phát hiện mất một quy tắc nghiệp vụ mà không được biểu diễn ở type system.** Bản `premature` hợp lệ về Java nhưng không bảo toàn hành vi.

Bài học rút ra: biết quan hệ class/subclass là chưa đủ; cần biết **ý nghĩa và thứ tự** các nhánh.

## 4. Năm bẫy khi chuyển legacy cast sang pattern matching

### 4.1. `getClass() == Type.class` khác `instanceof Type`

Code cũ có thể cố ý chỉ chấp nhận đúng class, loại subclass:

```java
if (message != null && message.getClass() == Text.class) {
    Text text = (Text) message;
    return "ordinary text:" + text.value();
}
```

Nếu chuyển thành:

```java
if (message instanceof Text text) {
    return "ordinary text:" + text.value();
}
```

thì `UrgentText` cũng được chấp nhận. Đây **không** phải thay đổi cú pháp tương đương. Phải tìm hiểu vì sao code cũ yêu cầu exact class trước khi thay đổi điều kiện.

### 4.2. Cast vô điều kiện khác với phép kiểm tra `instanceof` rồi fallback

Xét:

```java
static String strict(Object value) {
    Text text = (Text) value;
    return text.value();
}
```

- Nếu `value` chứa một kiểu không chuyển được thành `Text`, cast có thể ném `ClassCastException`.
- Nếu `value` là null, phép cast sang reference type cho ra null; lời gọi `text.value()` sau đó ném `NullPointerException`.

Thay bằng:

```java
static String permissive(Object value) {
    if (value instanceof Text text) {
        return text.value();
    }
    return "unsupported";
}
```

sẽ biến hai con đường lỗi thành kết quả `unsupported`. Việc này có thể phù hợp với một **thay đổi yêu cầu nghiệp vụ đã được duyệt**, nhưng **không phải refactor giữ nguyên hành vi**. Nếu các caller đang phụ thuộc vào exception, cần giữ hợp đồng hoặc phối hợp thay đổi caller và test.

### 4.3. Đổi thứ tự `if/else` hoặc dùng một pattern quá rộng

Ví dụ: đặt `if (message instanceof Text)` trước `if (message instanceof UrgentText)` làm nhánh `UrgentText` không còn đến được trong chuỗi `if`, dù compiler có thể không báo.

Với Java 21 `switch` pattern:

```java
// Mã minh họa KHÔNG BIÊN DỊCH:
// return switch (message) {
//     case Text text -> "text";
//     case UrgentText urgent -> "urgent"; // dominated
//     case null -> "null";
//     default -> "other";
// };
```

Ở đây compiler có thể phát hiện nhánh `UrgentText` bị bao phủ (dominated) bởi `Text`. Tuy nhiên, nếu người refactor **xóa hẳn** nhánh UrgentText để “sửa lỗi compiler”, luật nghiệp vụ vẫn bị mất. Cách đúng là tìm hiểu và giữ độ ưu tiên nhánh, không chỉ làm compiler hài lòng.

### 4.4. `switch` pattern có quy tắc xử lý null riêng

Với legacy `if (value instanceof Text)`, `null` làm điều kiện trả `false` và luồng đi qua fallback. Trong `switch` pattern Java 21, selector null không tự động chọn nhánh `default` như mọi kiểu chưa biết. Nếu không có nhánh null thích hợp, có thể gặp `NullPointerException`.

Nếu code cũ trả `unsupported` cho null, khi đổi sang switch cần nêu rõ:

```java
// Java 21+, đoạn minh họa trong phương thức nhận Message.
return switch (message) {
    case UrgentText urgent -> "urgent:" + urgent.value();
    case Text text -> "text:" + text.value();
    case Count count -> "count:" + count.value();
    case null -> "unsupported";
    default -> "unsupported";
};
```

Dù ví dụ có vẻ bảo toàn một phần hành vi, chỉ đổi sang `switch` sau khi kiểm tra tất cả các nhánh và tác động phụ. `case null` xử lý null của **selector**, không tự xử lý mọi component null bên trong một record pattern lồng nhau.

### 4.5. Getter, accessor và side effect

Code cũ đôi khi gọi getter đúng một lần ở một nhánh. Refactor thành nested record pattern có thể trích xuất component **trong quá trình khớp**, trước khi thực thi body. Nếu record có accessor tùy biến ghi log, tính toán, đọc trạng thái biến đổi hoặc ném ngoại lệ, thời điểm/số lần gọi có thể khác.

Ví dụ code minh họa:

```java
record LoggedValue(String text) {
    @Override
    public String text() {
        System.out.println("getter called");
        return text;
    }
}
```

Trước khi thay:

```java
// Mã minh họa không phải chương trình độc lập.
if (value instanceof LoggedValue logged) {
    String text = logged.text();
    process(text);
}
```

bằng một record pattern lồng nhau hoặc nhiều nhãn `case`, cần hiểu liệu việc gọi accessor có được phép gây tác động không. Không giả định mọi lần “thử pattern không khớp” đều vô hại, nhất là khi có lồng record patterns.

## 5. Type erasure: đừng “khôi phục” kiểu generic từ runtime

Mã cũ có thể chứa raw cast hoặc unchecked cast:

```java
// Code minh họa legacy, không được khuyến nghị.
@SuppressWarnings("unchecked")
static java.util.List<String> strings(Object value) {
    return (java.util.List<String>) value;
}
```

Dù cast này compile (có unchecked warning được suppress), JVM thường không thể phân biệt `List<String>` với `List<Integer>` dựa trên type arguments đã bị xóa. Refactor “tương đương” kiểu:

```java
// KHÔNG BIÊN DỊCH nếu input chỉ có kiểu Object:
// if (value instanceof java.util.List<String> list) { ... }
```

không tự trở thành hợp lệ chỉ vì ta sử dụng pattern matching.

Có thể kiểm tra container bằng `List<?>`:

```java
if (value instanceof java.util.List<?> list) {
    System.out.println("size=" + list.size());
}
```

nhưng điều đó **không chứng minh** mọi phần tử là String. Nếu domain thật sự yêu cầu danh sách chuỗi, cần hợp đồng kiểu ở API hoặc kiểm tra từng phần tử trước khi xử lý. Đừng che cảnh báo unchecked cast bằng một pattern trông có vẻ type-safe nhưng không bảo đảm invariant.

## 6. Dấu hiệu phải dừng refactor để hiểu domain

Hãy **dừng ở mức thay đổi cú pháp cục bộ** và chuyển sang thu thập bằng chứng nếu có một trong các dấu hiệu sau:

1. **Type hierarchy chưa kiểm kê:** interface được module khác triển khai, thư viện có class kế thừa, plugin có thể cung cấp subtype hoặc code dùng proxy.
2. **Thứ tự nhánh không rõ:** nhiều `instanceof` với kiểu cha/con, nhánh có guard đặc thù, hoặc nhánh có side effect xảy ra trước nhánh fallback.
3. **Dữ liệu bên ngoài không có schema ổn định:** API JSON, legacy database, sự kiện message queue, dữ liệu từ nhiều phiên bản hệ thống.
4. **Fallback có lịch sử xử lý lỗi:** trả mã mặc định, log, retry, dead-letter queue hoặc ném ngoại lệ; chưa rõ ai tiêu thụ kết quả đó.
5. **Null và dữ liệu không hợp lệ chưa có hợp đồng:** không biết null là trường hợp hợp lệ, vi phạm invariant hay tín hiệu đặc biệt.
6. **Có cast generic không kiểm tra được:** raw types, `Object` chứa collection, các warning bị suppress hoặc dữ liệu bị deserialize.
7. **Có tác động phụ:** ghi log/audit, metrics, trạng thái, cache, giao dịch hoặc gọi dịch vụ nằm trong điều kiện/getter/nhánh.
8. **Không có characterization tests:** không có bộ test mô tả hành vi hiện tại của các đường đi quan trọng.
9. **Cần thay đổi public API, sealed hierarchy hoặc serialization:** ảnh hưởng code ngoài phạm vi hiện tại.
10. **Muốn gộp case chỉ vì “chúng trông giống nhau”:** chưa có xác nhận rằng chúng thực sự tương đương về chính sách nghiệp vụ.

Những dấu hiệu này không cấm mọi thay đổi. Chúng có nghĩa **không nên thực hiện thay đổi semantics trên giả định**. Một sửa chữa bug có chủ ý vẫn hợp lệ, nhưng phải mô tả là thay đổi hành vi, không phải refactor thuần túy.

## 7. Cách thu thập bằng chứng trước khi quyết định

### 7.1. Xác định hợp đồng trước, cú pháp sau

Với từng nhánh legacy, ghi lại:

| Câu hỏi | Bằng chứng cần tìm |
| --- | --- |
| Nhánh nhận kiểu nào? | Khai báo class, subtypes, dữ liệu từ caller hoặc plugin |
| Điều kiện ưu tiên ra sao? | Thứ tự `if/else if`, so sánh `getClass` hay `instanceof` |
| Giá trị hợp lệ là gì? | Validation, schema, business rules, ví dụ dữ liệu thật đã ẩn thông tin nhạy cảm |
| Khi thất bại xảy ra điều gì? | Exception, fallback, logging, retry, mã trả về |
| Có side effect nào? | Đường gọi getter, database, event, metric, mutable state |
| Ai phụ thuộc hành vi này? | Contract API, downstream, test tích hợp, backward compatibility |

Không dựa hoàn toàn vào tên class: `UrgentText`, `PremiumUser` hay `SpecialRequest` có thể là tên gợi ý nhưng chưa đủ chứng minh luật xử lý.

### 7.2. Viết characterization tests

**Characterization test** ghi lại **hành vi hiện tại**, kể cả những hành vi khó hiểu. Mục tiêu ban đầu là bảo vệ những gì hệ thống đang làm trước khi đánh giá nên thay đổi gì.

Bộ tối thiểu nên bao gồm:

- Kiểu thường, subtype đặc biệt và subtype gần giống nhau.
- `null`, kiểu không hỗ trợ, dữ liệu trống, giá trị biên.
- Thứ tự chọn nhánh, output, exception type (khi thuộc hợp đồng).
- Tác động phụ quan sát được: một event/log quan trọng được ghi hay không, số lần gọi nghiệp vụ nếu hợp đồng yêu cầu.
- Các kiểu generic/wildcard hoặc dữ liệu từ API cũ nếu tồn tại.
- Trường hợp có phiên bản serialization cũ, hoặc data mẫu đã được kiểm duyệt.

Trong chương trình đầy đủ ở trên, cặp `legacy`/`safe` có cùng output ở năm trường hợp; nhưng `legacy`/`premature` khác nhau ở `urgent`. Bộ test chỉ có `Text` và `Count` sẽ bỏ sót regression này.

Nếu không thể xác định output mong đợi từ domain, ban đầu có thể “đóng băng” output hiện hành để phát hiện khác biệt, **không** mặc nhiên khẳng định hành vi cũ là đúng.

### 7.3. Phân biệt test so sánh với shadow execution

Một ý tưởng phổ biến là chạy cả logic cũ và mới rồi so sánh. Chỉ an toàn khi hai đường đi **thuần túy, không có side effect**. Không chạy song song hai phiên bản nếu chúng đều có thể trừ tiền, ghi database, gửi email hoặc phát message.

Đối với hàm có side effect, dùng test cô lập với mock/fake, môi trường thử nghiệm có kiểm soát hoặc tái hiện input từ log đã được xử lý an toàn. Cần đo cả output, exception và tác động phụ, không chỉ so sánh chuỗi trả về.

## 8. Lộ trình refactor thận trọng

### Bước 1 — Khoanh phạm vi thay đổi

Chọn một nhánh `instanceof + cast` có quan hệ rõ ràng, ít rủi ro. Không tiện tay đổi thứ tự xử lý, thay contract null hoặc thay interface thành sealed trong cùng bước.

### Bước 2 — Giữ nguyên điều kiện và fallback

Áp dụng phép biến đổi cục bộ:

```java
// Trước:
if (value instanceof Text) {
    Text text = (Text) value;
    return text.value();
}

// Sau:
if (value instanceof Text text) {
    return text.value();
}
```

Chỉ coi tương đương khi `value` là cùng một biểu thức/đối tượng, không có thay đổi trạng thái ở giữa và phần thân/fallback giữ nguyên.

### Bước 3 — Chạy test bảo toàn hành vi

Chạy characterization tests, test tích hợp và các đường đi subtype/null/error. Nếu xuất hiện khác biệt, phân loại thành:

- **Regression không chủ ý:** hoàn tác thay đổi hoặc sửa để khôi phục hành vi cũ.
- **Bug cũ có bằng chứng:** mở một thay đổi nghiệp vụ riêng, có acceptance criteria.
- **Domain chưa xác định:** chưa merge refactor lớn; xin xác nhận hợp đồng từ người phụ trách module.

### Bước 4 — Chỉ mở rộng dùng `switch`/record patterns khi có lý do

Sau khi chứng minh mọi nhánh và null/fallback, có thể cân nhắc `switch` pattern (Java 21) để phân loại rõ hơn. Nếu đề xuất nested record patterns, cần xác nhận dữ liệu có record structure ổn định và accessor có phù hợp với việc deconstruct không. Nếu đề xuất `sealed`, phải kiểm tra các implementation có thể tồn tại.

### Bước 5 — Quan sát sau triển khai

Đối với hệ thống nhận dữ liệu bên ngoài, theo dõi tần suất nhánh fallback, kiểu chưa biết và lỗi chuyển kiểu. Không ghi dữ liệu nhạy cảm vào log chỉ để xác định domain. Khi hành vi đã được hiểu, các thay đổi sâu hơn nên tách thành những PR có test và mục tiêu rõ ràng.

## 9. Khi nào việc chưa refactor là quyết định tốt?

Một quyết định **chưa đổi kiến trúc** có thể là quyết định kỹ thuật chủ động nếu:

- Mã legacy hoạt động ổn định, rủi ro chạm tới domain cao và chưa có test bao phủ.
- Một hệ thống plugin có implementation từ bên ngoài; đổi sang sealed hierarchy có thể phá tương thích.
- Nhánh fallback thực hiện tác vụ quan trọng nhưng chưa được tài liệu hóa.
- Type erasure hoặc dữ liệu deserialize khiến kiểu thật ở runtime không thể xác định tin cậy.
- Có yêu cầu delivery gấp: thay đổi cú pháp nhỏ, kiểm thử được, tốt hơn một lần refactor lớn chưa được chứng minh.

Nên để lại ghi chú rõ ràng trong issue/PR về **điểm chưa biết, bằng chứng cần thu thập và điều kiện để tiếp tục**, thay vì bình luận mơ hồ “legacy code, TODO refactor”.

Ví dụ ghi chú ngắn:

> Giữ thứ tự `UrgentText` trước `Text` vì có khác biệt output hiện hành. Chưa xác nhận tất cả implementations của `Message` từ plugin; giai đoạn này chỉ thay cast bằng pattern variables, giữ nguyên fallback và exception behavior. Cần characterization tests cho plugin messages trước khi chuyển toàn bộ logic sang switch.

## 10. Những lỗi tư duy phổ biến

1. **“Compile được thì semantics chắc không đổi.”** Compiler chỉ kiểm tra quy tắc ngôn ngữ; nó không biết mọi quy tắc nghiệp vụ.
2. **“Pattern matching luôn an toàn hơn cast.”** Type pattern giúp tránh một số cast thừa, nhưng không tự giữ exception, fallback và side effect cũ.
3. **“Nhánh subtype là trường hợp của nhánh cha nên có thể gộp.”** Đúng về quan hệ kiểu, chưa chắc đúng về domain.
4. **“Không thấy subtype trong repo nghĩa là không tồn tại.”** Có thể có plugin, dependency, subclass ở module khác hoặc dữ liệu triển khai.
5. **“`default` của switch sẽ xử lý mọi thứ như legacy else.”** Selector null có quy tắc riêng trong pattern switch; còn default có thể thay đổi exception behavior.
6. **“Record pattern chỉ viết ít code hơn.”** Deconstruction có quy tắc gọi accessor và null; có thể thay đổi thời điểm lỗi/tác động.
7. **“Unchecked cast có thể đổi thành `List<String>` pattern.”** Java type erasure không cho phép chứng minh thông tin generic như vậy từ một `Object`.
8. **“Có một test happy path là đủ.”** Regression quan trọng thường ở subclass, null, unknown type và giá trị biên.
9. **“Có thể shadow-run cả hai nhánh để so sánh.”** Không nếu logic có side effect lên hệ thống thật.
10. **“Không refactor là bỏ mặc code.”** Đặt giới hạn thay đổi và thu thập hợp đồng là phần thiết yếu của bảo trì hệ thống.

## 11. Checklist trước khi phê duyệt PR

- [ ] Scope có chỉ là thay cú pháp, hay có thay đổi domain/behavior?
- [ ] Các nhánh subtype/parent và thứ tự được giữ nguyên hoặc có yêu cầu mới được phê duyệt?
- [ ] `null`, kiểu không hỗ trợ, exception và fallback đã có test?
- [ ] Những getter, record accessor, guards và nhánh có side effect được kiểm tra?
- [ ] Generic type erasure, raw types hoặc unchecked cast đã được đánh giá?
- [ ] Không thêm `sealed`, đổi API hoặc thay serialization khi chưa biết mọi consumers?
- [ ] Có characterization tests cho các trường hợp domain quan trọng và regression được đối chiếu?
- [ ] Nếu có behavior change, PR nói rõ *đã thay đổi gì, vì sao, ai xác nhận và tác động tới caller*?

**Kết luận:** Khi domain chưa rõ, ưu tiên **refactor cơ học có phạm vi hẹp** (như thay `instanceof + cast` bằng pattern variable trong cùng nhánh) và giữ nguyên hành vi quan sát được. **Trì hoãn** việc gộp nhánh, chuyển hoàn toàn sang switch/record patterns, sửa exception/fallback hoặc đóng phân cấp kiểu cho đến khi có hợp đồng và bằng chứng kiểm thử. Mục tiêu của pattern matching là giúp code rõ hơn, không phải che mất những quy tắc nghiệp vụ chưa được hiểu.

### Tài liệu tham khảo

- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
