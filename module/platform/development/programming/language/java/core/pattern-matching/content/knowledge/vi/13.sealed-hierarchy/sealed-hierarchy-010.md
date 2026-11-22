# Rủi ro khi sealed hierarchy thay đổi trong Java Pattern Matching

Một **sealed hierarchy** cho phép Java giới hạn những lớp hoặc interface nào được trực tiếp kế thừa một kiểu. Nhờ danh sách `permits`, compiler Java 21 có thể kiểm tra một `switch` pattern matching đã **exhaustive** (bao phủ toàn bộ kiểu con có thể xảy ra) mà không cần viết `default`.

Điều này rất hữu ích khi thiết kế domain có tập trường hợp rõ ràng. Nhưng khi hierarchy được sửa—thêm subtype, xóa subtype, mở một nhánh `non-sealed` hoặc thay đổi kiểu con—các `switch` phụ thuộc vào cấu trúc cũ có thể bị ảnh hưởng. Đặc biệt, **một chương trình đã biên dịch từ trước có thể tiếp tục liên kết được với thư viện mới nhưng ném `MatchException` khi gặp subtype mới không có nhánh xử lý**.

> **Cần nhớ:** “Exhaustive lúc biên dịch” không có nghĩa là “tự xử lý mọi phiên bản hierarchy trong tương lai”. Thay đổi sealed hierarchy là thay đổi hợp đồng kiểu và cần kiểm tra cả **source recompilation**, **runtime compatibility** lẫn **ý nghĩa nghiệp vụ của từng case**.

Bài này phân tích rủi ro, cách kiểm tra và chiến lược thiết kế trong **Java Core Pattern Matching**. Cú pháp `sealed`, `permits` và `non-sealed` ổn định từ **Java 17**; pattern matching cho `switch` và `case null` ổn định từ **Java 21**. Các chương trình có type pattern trong `switch` cần JDK 21+.

## 1. Vì sao `sealed` giúp compiler xác định exhaustive?

Giả sử một API định nghĩa hai loại sự kiện:

```java
sealed interface Event permits Added, Removed {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}
```

Ở đây `Event` chỉ cho phép hai **direct permitted subtypes** là `Added` và `Removed`. Cả hai là `record`, nên đều là kiểu `final`: không thể có lớp con khác của chúng.

Java 21 chấp nhận:

```java
static String describe(Event event) {
    return switch (event) {
        case Added a -> "added:" + a.id();
        case Removed r -> "removed:" + r.id();
    };
}
```

Không có `default` mà `switch expression` vẫn exhaustive, vì mọi đối tượng khác `null` thuộc kiểu `Event` hợp lệ trong hierarchy hiện tại đều phải là `Added` hoặc `Removed`.

Sự bảo đảm này dựa vào **thông tin kiểu lúc biên dịch**. Nó không phải một bộ kiểm tra tự động cập nhật khi một JAR khác chứa phiên bản mới của `Event` được thay thế trong môi trường chạy.

### Phạm vi của `permits`

Một sealed class/interface liệt kê **những kiểu được phép kế thừa trực tiếp**, không phải danh sách tất cả object sẽ tồn tại mãi mãi. Mỗi direct subtype hợp lệ phải đi theo một trong những hướng:

- **`final`**: không cho phép kế thừa tiếp; `record` mặc nhiên `final`.
- **`sealed`**: tiếp tục giới hạn subtype được phép ở tầng kế tiếp.
- **`non-sealed`**: cho phép mở rộng nhánh này bằng các lớp con khác.

Những direct permitted subtypes phải tuân theo quy tắc vị trí/module của Java: cùng named module, hoặc cùng package nếu dùng unnamed module. Khi đổi hierarchy, cần biên dịch các khai báo kiểu phù hợp, không chỉ sửa một chuỗi trong `permits`.

## 2. Chương trình Java 21+ ban đầu: exhaustive, không `default`

Lưu **`SealedExhaustiveDemo.java`**:

```java
sealed interface Event permits Added, Removed {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}

public class SealedExhaustiveDemo {
    static String describe(Event event) {
        return switch (event) {
            case Added a -> "added:" + a.id();
            case Removed r -> "removed:" + r.id();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Added("A7")));
        System.out.println(describe(new Removed("B2")));

        try {
            System.out.println(describe(null));
        } catch (NullPointerException ex) {
            System.out.println("null: NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SealedExhaustiveDemo.java
java SealedExhaustiveDemo
```

Kết quả:

```text
added:A7
removed:B2
null: NullPointerException
```

**Hai điểm khác nhau:** Các subtype đã được bao phủ nên compiler không bắt viết `default`. Nhưng `null` **không phải một subtype của `Event`**; khi selector của `switch` là `null` mà không có `case null`, Java ném `NullPointerException`. Không nên gộp vấn đề null với vấn đề thêm subtype mới.

Nếu API cho phép `null`, có thể bổ sung `case null`. Nếu `null` bị cấm, kiểm tra tại boundary bằng `Objects.requireNonNull` hoặc giữ hợp đồng từ chối giá trị không hợp lệ.

## 3. Khi thư viện thêm subtype: hai tình huống hoàn toàn khác

Phiên bản tiếp theo của mô hình muốn hỗ trợ thêm sự kiện cập nhật:

```java
// Phiên bản V2 của mô hình:
sealed interface Event permits Added, Removed, Updated {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}
record Updated(String id) implements Event {}
```

Giờ `Event` có thêm một permitted direct subtype. Một `switch` cũ chỉ xử lý `Added`/`Removed` chịu hai rủi ro tùy cách triển khai.

### 3.1. Biên dịch lại client cũ với thư viện mới

```java
// KHÔNG BIÊN DỊCH với Event V2:
static String describe(Event event) {
    return switch (event) {
        case Added a -> "added:" + a.id();
        case Removed r -> "removed:" + r.id();
    };
}
```

Compiler nhìn thấy `Updated` cũng có thể xuất hiện, nên báo `switch expression` **không bao phủ mọi giá trị đầu vào**. Đây là lỗi *non-exhaustive switch* ở **compile time**. Nó là tín hiệu hữu ích: nhà phát triển phải quyết định xử lý `Updated` như thế nào.

Một cách sửa tốt là **thêm case rõ ràng** cho loại mới, thay vì thêm `default -> "unknown"` chỉ để compiler ngừng báo lỗi.

### 3.2. Giữ client binary cũ nhưng triển khai thư viện mới

Một kịch bản khác có thể nguy hiểm hơn:

```text
Library V1: Event permits Added, Removed
    |
    +--> Client V1 được biên dịch:
         switch(Event) { case Added; case Removed; }
         Compiler kết luận: exhaustive
    |
    v
Library V2: Event permits Added, Removed, Updated
    |
    +--> Thay library V1 bằng V2
         nhưng KHÔNG biên dịch lại client V1
    |
    v
Client V1 nhận instance Updated
    |
    +--> Không có case nào khớp
         -> có thể ném java.lang.MatchException
```

Theo tài liệu Oracle Java 21, khi một `switch` được compiler coi exhaustive nhưng runtime gặp giá trị không khớp pattern nào do **separate compilation** và hierarchy đã được sửa, có thể ném **`MatchException`**.

Điều này **không mâu thuẫn** với việc thêm một permitted subtype có thể vẫn *binary compatible*: class cũ vẫn link được với thư viện mới, nhưng giả định exhaustive đã lỗi thời khi một instance thuộc subtype mới đi qua `switch` cũ.

| Thao tác | Tình huống | Hệ quả |
| --- | --- | --- |
| Recompile client với thư viện V2 | Case cũ thiếu `Updated` | Compiler báo non-exhaustive |
| Chạy client binary V1 với thư viện V2 | Nhận `Updated`, không case nào phù hợp | Có thể ném `MatchException` |
| Recompile client đã thêm `case Updated` | Tất cả subtype được xử lý | Biên dịch thành công |
| Client có `default` từ trước | Nhận `Updated` ở runtime | Có thể chạy fallback, tùy chính sách được viết |
| Client chỉ nhận `Added`/`Removed` như trước | Chưa gặp subtype mới | Có thể tiếp tục chạy bình thường, nhưng rủi ro vẫn tồn tại |

**Không giả định mọi lần nâng version đều ném `MatchException`.** Ngoại lệ xảy ra khi một đường thực thi gặp giá trị không được các case xử lý. Một pattern rộng hoặc `default` đã tồn tại có thể áp dụng cho subtype mới.

## 4. Cập nhật đúng: xử lý subtype mới một cách tường minh

Lưu **`EvolvedHierarchyDemo.java`**:

```java
sealed interface EvolvedEvent permits NewAdded, NewRemoved, Updated {}

record NewAdded(String id) implements EvolvedEvent {}
record NewRemoved(String id) implements EvolvedEvent {}
record Updated(String id) implements EvolvedEvent {}

public class EvolvedHierarchyDemo {
    static String describe(EvolvedEvent event) {
        return switch (event) {
            case null -> "missing";
            case NewAdded a -> "added:" + a.id();
            case NewRemoved r -> "removed:" + r.id();
            case Updated u -> "updated:" + u.id();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new NewAdded("A7")));
        System.out.println(describe(new Updated("C3")));
        System.out.println(describe(null));
    }
}
```

```bash
javac EvolvedHierarchyDemo.java
java EvolvedHierarchyDemo
```

Kết quả:

```text
added:A7
updated:C3
missing
```

Mọi direct subtype của `EvolvedEvent` đều có case; `null` có nhánh riêng. Ta vẫn không cần `default`. Nếu thêm subtype thứ tư rồi biên dịch lại, compiler tiếp tục có thể phát hiện điểm xử lý chưa đủ.

Trong một ứng dụng thật, không nhất thiết phải đổi tên toàn bộ kiểu khi thêm subtype. Các tên `EvolvedEvent`/`NewAdded`/`NewRemoved` ở ví dụ này chỉ giúp chương trình đứng độc lập và không trùng tên với chương trình mẫu V1.

## 5. Binary compatibility khác migration compatibility thế nào?

Đây là điểm nhiều tài liệu về sealed hierarchy dễ bị đọc nhầm.

**Binary compatibility** nghĩa là binary được biên dịch trước đó tiếp tục liên kết được với một thay đổi thư viện theo quy tắc JVM/JLS. Theo JLS Java 21, **thêm một permitted direct subtype** vào sealed class/interface là thay đổi có thể **binary compatible** với binary cũ.

**Source recompilation compatibility** là câu hỏi khác: khi biên dịch lại source client với kiểu mới, mọi yêu cầu compile-time có còn được đáp ứng không? `switch` thiếu subtype mới có thể không còn exhaustive, nên **biên dịch lại thất bại** cho tới khi cập nhật case.

**Migration compatibility** xét liệu chương trình cũ khi chạy cùng phiên bản thư viện mới có hoạt động đúng không. Một `switch` đã được biên dịch với tập subtype cũ có thể gặp subtype mới rồi ném `MatchException`, hoặc chạy một fallback không đúng nghiệp vụ.

Nói ngắn gọn:

```text
Binary compatible:
    binary cũ có thể vẫn link được

Source recompilation:
    switch cũ có thể không còn exhaustive và không compile

Migration compatible:
    phải xem binary cũ sẽ làm gì khi subtype mới xuất hiện
```

Do đó **“không phá binary compatibility” không phải cam kết “không ảnh hưởng runtime behavior”**. Khi bảo trì API có consumer phân tán, cần kiểm tra cả hai phương diện.

### Nếu xóa subtype khỏi `permits` thì sao?

Thay đổi ngược lại cũng có rủi ro. Nếu một direct subtype bị loại khỏi tập permitted nhưng **binary cũ của subtype đó vẫn được tải**, Java có thể ném **`IncompatibleClassChangeError`** khi lớp cũ không còn được phép trực tiếp kế thừa sealed parent. Đây là lỗi liên kết/kế thừa, không phải cùng cơ chế `MatchException` của exhaustive switch.

Không nên gộp hai nhận định “thêm subtype” và “xóa subtype” thành một quy tắc tương thích duy nhất; JLS có quy tắc riêng cho từng kiểu tiến hóa của sealed class/interface.

## 6. `default`: tiện cho tương thích nhưng có thể che lỗi thiếu case

Một cách thường gặp là thêm fallback:

```java
static String describe(Event event) {
    return switch (event) {
        case Added a -> "added:" + a.id();
        case Removed r -> "removed:" + r.id();
        default -> "unknown";
    };
}
```

Trong hierarchy V1, `default` có thể không xử lý đối tượng hợp lệ nào ngoài những trường hợp đặc biệt. Nhưng sau khi thêm `Updated`, `switch` trên có thể biên dịch bình thường và đưa `Updated` vào `default`.

**Điểm tốt:**

- Có chính sách cho subtype chưa được consumer biết.
- Có thể tránh việc rơi vào trạng thái không case khớp ở đúng điểm `switch` đó.
- Hữu ích tại ranh giới nhận dữ liệu có version khác, nếu “unknown type” là trạng thái có thể xử lý.

**Điểm nguy hiểm:**

- Compiler **không còn ép bạn cập nhật case** khi một subtype quan trọng được bổ sung.
- `default -> "unknown"` có thể âm thầm loại bỏ ý nghĩa của loại mới.
- Với domain cần xử lý chính xác từng sự kiện, fallback bỏ qua dữ liệu có thể tệ hơn ném exception.
- `default` **không nhận selector `null`**; nếu `null` hợp lệ, vẫn cần `case null` hoặc `case null, default` theo chính sách.

Ví dụ: một sự kiện `Updated` có thể cần cập nhật trạng thái đơn hàng. Nếu `default` chỉ trả `"ignored"`, chương trình không crash nhưng trạng thái nghiệp vụ bị sai. Vì thế, **compile success không đủ là bằng chứng đúng logic**.

## 7. Fallback fail-fast có chủ đích

Khi hệ thống phải chạy nhiều phiên bản nhưng không được âm thầm xử lý sai subtype mới, có thể dùng `default` để ném lỗi có thông tin.

Lưu **`ExplicitFallbackDemo.java`**:

```java
sealed interface Event permits Added, Removed {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}

public class ExplicitFallbackDemo {
    static String describe(Event event) {
        return switch (event) {
            case null -> "missing";
            case Added a -> "added:" + a.id();
            case Removed r -> "removed:" + r.id();
            default -> throw new IllegalStateException(
                    "Unknown subtype: " + event.getClass().getSimpleName());
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Added("A7")));
        System.out.println(describe(new Removed("B2")));
        System.out.println(describe(null));
    }
}
```

```bash
javac ExplicitFallbackDemo.java
java ExplicitFallbackDemo
```

Kết quả:

```text
added:A7
removed:B2
missing
```

Nếu một subtype mới trở thành hợp lệ sau khi thư viện được cập nhật và đi vào binary client có nhánh `default` này, nó sẽ bị từ chối bằng `IllegalStateException` mang tên subtype thay vì âm thầm nhận một kết quả giả như `"unknown"`.

**Quan trọng:** Trong chương trình mẫu hiện tại chưa có `Updated` thuộc `Event`, nên không giả vờ rằng đầu ra của subtype mới đã được chạy trong phiên bản đó. Đây là **chính sách dự kiến khi hierarchy tiến hóa**.

`event.getClass()` an toàn trong nhánh `default` của ví dụ vì `case null` đã được khai báo. Nếu selector `null` mà không có `case null`, chính `switch` sẽ ném NPE trước khi vào `default`.

**Đánh đổi:** dùng `default` fail-fast làm lỗi runtime dễ hiểu hơn, nhưng **không thay thế được ưu điểm kiểm tra exhaustive tại biên dịch lại**. Tác giả phải chủ động kiểm tra contract khi thêm subtype.

## 8. Nhánh `non-sealed` và phạm vi mở rộng thực sự

Không phải mọi sealed hierarchy đều đóng hoàn toàn ở mức leaf class. Ví dụ:

```java
sealed interface Notice permits Heartbeat, PluginNotice {}

record Heartbeat(int sequence) implements Notice {}
non-sealed class PluginNotice implements Notice {}
```

Nhờ `non-sealed`, người phát triển có thể thêm các lớp con của `PluginNotice` mà không chỉnh `permits` ở `Notice`:

```java
final class ExtraNotice extends PluginNotice {}
```

Một `switch` có nhánh `case PluginNotice p` **bao phủ cả các lớp con** của `PluginNotice`, kể cả lớp được bổ sung sau:

```java
static String route(Notice notice) {
    return switch (notice) {
        case Heartbeat h -> "heartbeat:" + h.sequence();
        case PluginNotice p -> "plugin";
    };
}
```

Nếu mọi plugin notice cùng một chiến lược xử lý, đây là cách hợp lý để một sealed hierarchy vẫn cho phép mở rộng ở một nhánh có kiểm soát.

### Ví dụ Java 21+ hoàn chỉnh

Lưu **`NonSealedBranchDemo.java`**:

```java
sealed interface Notice permits Heartbeat, PluginNotice {}

record Heartbeat(int sequence) implements Notice {}
non-sealed class PluginNotice implements Notice {}
final class ExtraNotice extends PluginNotice {}

public class NonSealedBranchDemo {
    static String route(Notice n) {
        return switch (n) {
            case null -> "missing";
            case Heartbeat h -> "heartbeat:" + h.sequence();
            case PluginNotice p -> "plugin";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(new Heartbeat(9)));
        System.out.println(route(new ExtraNotice()));
        System.out.println(route(null));
    }
}
```

```bash
javac NonSealedBranchDemo.java
java NonSealedBranchDemo
```

Đầu ra:

```text
heartbeat:9
plugin
missing
```

Nếu xuất hiện `AnotherNotice extends PluginNotice`, case `PluginNotice` vẫn có thể nhận nó. Nhưng nếu một plugin notice mới cần xử lý khác, case quá rộng lại có nguy cơ che khuất yêu cầu nghiệp vụ mới. **Bao phủ về kiểu không đồng nghĩa xử lý đúng về nghĩa.**

Khi chỉ liệt kê một vài concrete subclass của `PluginNotice` mà không có case cho chính nhánh mở, compiler có thể coi `switch` thiếu bao phủ. Điều này phản ánh việc nhánh `non-sealed` cho phép các subtype chưa biết xuất hiện.

## 9. Những loại thay đổi cần đặc biệt chú ý

| Thay đổi hierarchy | Rủi ro cần kiểm tra |
| --- | --- |
| Thêm direct subtype vào `permits` | Exhaustive switch cũ bị thiếu case khi recompile; binary cũ có thể gặp `MatchException` |
| Thêm subtype trong một sealed branch ở tầng sâu | Switch chỉ xử lý các leaf cũ có thiếu kiểu mới không? |
| Thêm subclass của `non-sealed` | Case cho nhánh `non-sealed` có nhận subclass mới và xử lý đúng không? |
| Xóa direct subtype khỏi `permits` | Binary của subtype cũ có bị lỗi khi load (`IncompatibleClassChangeError`) không? |
| Thay đổi `final`, `sealed` hoặc `non-sealed` | Có làm mở rộng hoặc thu hẹp tập kiểu runtime được phép không? |
| Chuyển một hierarchy kín sang khả năng kế thừa mở | Những `switch` dựa trên exhaustiveness có còn biên dịch được không? |
| Đổi generic bounds hoặc type arguments | Type coverage trên một generic sealed selector có thay đổi không? |
| Thêm guarded pattern `when` | Guard có thể false, ảnh hưởng tính exhaustive và case tiếp theo không? |
| Thêm pattern rộng hoặc `default` | Có khiến subtype mới bị xử lý chung hoặc một case bị dominance không? |

Một `switch` không nhất thiết phải có **một case cho mỗi tên direct subtype**. Java xét **type coverage**; một pattern rộng có thể bao phủ nhiều subtype. Với generic sealed types, compiler còn xét type argument của selector để xác định những subtype nào thực sự áp dụng. Vì vậy, phân tích rủi ro cần dựa trên **kiểu selector, subtype relation và các case cụ thể**, không chỉ đếm số dòng trong `permits`.

## 10. Tác động đến `when` guard và dominance

Giả sử ta đã viết:

```java
static String classify(Event event) {
    return switch (event) {
        case Added a when a.id().startsWith("A") -> "priority-add";
        case Added a -> "add";
        case Removed r -> "remove";
    };
}
```

*Đây là phương thức minh họa, cần đặt trong môi trường có `Event`/`Added`/`Removed` đã định nghĩa.*

Ở hierarchy ban đầu, có case `Added` không guard xử lý mọi `Added` chưa qua điều kiện, cùng case `Removed`. Nhưng khi thêm `Updated`, guard trên `Added` **không thể bao phủ `Updated`**. Compiler có thể báo non-exhaustive khi biên dịch lại.

Một guard `when` chỉ **giới hạn điều kiện áp dụng của pattern đã khớp**. Nó không tự nhận mọi subtype trong sealed hierarchy. Nếu guard có thể `false` thì nhánh còn lại phải xử lý những giá trị chưa được chọn theo yêu cầu exhaustive.

Ngoài ra, khi thêm case mới:

- Đặt pattern hẹp trước pattern rộng không guard để tránh dominance.
- Một pattern rộng không guard đặt trước có thể khiến case subtype phía sau bị compiler từ chối.
- `when true` được xử lý tương tự không guard khi xét dominance; guard bình thường có thể false.
- Kiểm tra null selector riêng: `case null` không được thay thế bởi một type pattern với guard.
- Đừng thêm `default` chỉ để làm im lỗi compiler mà chưa biết subtype mới cần xử lý thế nào.

## 11. Phân biệt `MatchException`, NPE và lỗi liên kết

| Tên lỗi | Nguyên nhân điển hình | Việc cần làm |
| --- | --- | --- |
| `MatchException` | `switch` đã được coi exhaustive lúc compile nhưng runtime không có pattern phù hợp, ví dụ sealed hierarchy bị thay đổi | So sánh binary client và phiên bản model, kiểm tra giá trị subtype thực tế |
| `NullPointerException` | Selector `switch` là `null` nhưng thiếu `case null` | Xác nhận hợp đồng null, thêm xử lý hoặc từ chối đầu vào rõ ràng |
| `IncompatibleClassChangeError` | Một class cũ không còn được phép trực tiếp kế thừa sealed parent mới hoặc vi phạm tương thích liên kết | Kiểm tra `permits`, JAR, module path và class loader |
| `IllegalStateException` do chương trình ném | `default` fail-fast nhận giá trị không được hỗ trợ | Đọc thông điệp; xem đã cần case mới hay thay đổi policy chưa |
| Compile error non-exhaustive | Source switch không bao phủ miền kiểu mới | Thêm case hoặc fallback theo yêu cầu nghiệp vụ |

**Không phải mọi `MatchException` đều do thêm subtype.** Java 21 còn có những trường hợp exhaustive pattern matching thất bại do nested record patterns hoặc component `null` không khớp các pattern được khai báo. Phải kiểm tra stack trace, loại pattern, dữ liệu thực tế và version của hierarchy trước khi kết luận.

Và **`default` không phải `catch`**: nếu expression của selector hay guard ném exception, Java không tự đi vào `default` để phục hồi.

## 12. Ba lựa chọn thiết kế khi biết hierarchy sẽ tiến hóa

### A. Không `default`: để compiler buộc xử lý mỗi subtype

```java
return switch (event) {
    case Added a -> handleAdded(a);
    case Removed r -> handleRemoved(r);
};
```

*Đoạn minh họa giả định `handleAdded` và `handleRemoved` trả về kiểu tương thích.*

Phù hợp khi domain thực sự đóng, từng subtype có logic riêng và có thể biên dịch lại toàn bộ consumer. Khi thêm subtype, lỗi non-exhaustive buộc cập nhật. Đánh đổi: client binary cũ có thể gặp `MatchException` nếu bị triển khai cùng thư viện mới mà chưa rebuild.

### B. `default` fail-fast: hỗ trợ phát hiện runtime version skew

```java
return switch (event) {
    case Added a -> handleAdded(a);
    case Removed r -> handleRemoved(r);
    default -> throw new IllegalStateException(
            "Unhandled Event subtype: " + event.getClass().getName());
};
```

Phù hợp với hệ thống versioned API có thể gặp subtype chưa biết nhưng **không được silently ignore**. Hành vi lỗi rõ hơn, có thể giám sát. Đánh đổi: compiler không báo thiếu case khi thêm subtype vì đã có `default`; cần quy trình review/test bù lại.

### C. Pattern cho nhánh mở rộng: polymorphism/strategy

```java
return switch (notice) {
    case Heartbeat h -> handleHeartbeat(h);
    case PluginNotice p -> handleAnyPlugin(p);
};
```

Phù hợp nếu mọi subtype của `PluginNotice` chia sẻ một chính sách, hoặc handler đa hình được gọi từ nhánh này. Đổi lại, phải kiểm tra rằng subtype mới không bị xử lý chung sai.

Không nhất thiết áp dụng một chiến lược trên toàn hệ thống. Domain lõi có thể exhaustive không `default`, còn integration boundary có explicit fallback, và extension point dùng một nhánh `non-sealed`.

## 13. Rủi ro khi triển khai nhiều phiên bản

Nhiều hệ thống không triển khai thư viện và client cùng lúc:

- Model/SDK được nâng cấp, nhưng consumer vẫn chạy class đã biên dịch với model cũ.
- Một rolling deployment có thể có các instance chạy phiên bản khác nhau.
- Producer mới bắt đầu gửi event subtype mới trong khi một số consumer chưa hỗ trợ.
- Cache, queue hoặc database lưu dữ liệu từ phiên bản khác, sau đó được giải mã thành subtype mới.
- Một adapter/plugin thêm lớp con của một nhánh `non-sealed` ngoài tập subtype mà consumer từng thử nghiệm.

Trong mỗi tình huống, **chỉ chạy unit test của model mới chưa đủ**. Cần biên dịch lại và chạy test cho consumer phụ thuộc, đặc biệt các lệnh `switch` exhaustive trong bản build cũ.

Một lỗi khác là “bản mới không crash nên an toàn”. Nếu subtype mới đi vào `default -> "ignored"`, hệ thống có thể âm thầm bỏ mất dữ liệu nghiệp vụ. Nên xác định rõ policy cho unknown subtype: trả kết quả được đánh dấu không hỗ trợ, log và cách ly để xử lý sau, hoặc fail-fast tùy hợp đồng.

## 14. Checklist nâng cấp sealed hierarchy an toàn

Khi chuẩn bị thay đổi `permits` hoặc cấu trúc subtype:

1. **Tìm mọi consumer của sealed type**, gồm `switch`, `instanceof` chains, serializer, handler registry và adapter.
2. **Phân loại chính xác thay đổi:** thêm direct subtype, xóa subtype, mở nhánh `non-sealed` hay sửa hierarchy nhiều tầng.
3. **Biên dịch lại consumer với dependency mới.** Không chỉ biên dịch module định nghĩa sealed type.
4. **Xử lý lỗi non-exhaustive có chủ đích.** Thêm case mới phản ánh nghiệp vụ, không chỉ thêm `default` để bỏ qua.
5. **Thử mỗi subtype hiện có và subtype mới.** Xác minh kết quả lẫn side effect, không chỉ rằng code chạy qua.
6. **Test version skew nếu có rolling release:** client cũ + library mới; client mới + library cũ khi hợp lý.
7. **Kiểm tra null độc lập.** `null` không là một subtype; xử lý qua `case null` hoặc contract không cho phép null.
8. **Kiểm tra nhánh `non-sealed`.** Thử một subclass mới không có trong bộ test trước để xác nhận pattern rộng thật sự có chính sách đúng.
9. **Kiểm tra classpath/module path và các artifact cũ.** Một subtype bị xóa khỏi `permits` nhưng binary vẫn còn có thể gây lỗi liên kết.
10. **Định nghĩa hành vi unknown type tại boundary.** Không silently ignore dữ liệu quan trọng; cung cấp logging/metrics và thông điệp lỗi có ích.
11. **Quan sát sau triển khai:** theo dõi `MatchException`, subtype không biết, và trường hợp fallback bất thường.
12. **Duy trì test hồi quy.** Mỗi lần thêm subtype phải có test cho việc xử lý đúng ở consumer, kể cả khi `switch` có `default`.

### Bảng tự kiểm thử

```text
[ ] Build client với sealed hierarchy mới
[ ] Mọi subtype hợp lệ có hành vi được xác nhận
[ ] Subtype mới không bị default/handler chung xử lý sai
[ ] Test binary cũ + library mới nếu hai version có thể cùng tồn tại
[ ] null selector có chính sách tường minh
[ ] non-sealed branch hỗ trợ hoặc từ chối subclass mới có chủ đích
[ ] Không còn JAR/module cũ vi phạm permits
[ ] Có log, cảnh báo hoặc test cho MatchException/unknown subtype
```

## 15. Các nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “Sealed nên danh sách subtype không bao giờ thay đổi.” | Chủ sở hữu thư viện vẫn có thể phát hành version mới với `permits` khác |
| “Đã exhaustive thì không bao giờ ném `MatchException`.” | Runtime có thể gặp subtype mới sau separate compilation; exhaustive cũ đã lỗi thời |
| “Thêm subtype là chắc chắn phá binary compatibility.” | JLS xem việc thêm permitted direct subtype là binary compatible với binary cũ trong điều kiện phù hợp, nhưng có rủi ro migration |
| “Client cũ chạy được với subtype cũ nghĩa là đã hỗ trợ subtype mới.” | Vấn đề chỉ xuất hiện khi đường chạy thật sự nhận subtype chưa được xử lý |
| “Thêm `default` luôn tốt hơn.” | `default` có thể che lỗi thiếu case và gây bug nghiệp vụ |
| “Không có `default` thì không bao giờ biên dịch được.” | Sealed hierarchy có thể giúp `switch expression` exhaustive mà không cần `default` |
| “`non-sealed` phá hoàn toàn exhaustiveness.” | Case trên chính kiểu nhánh `non-sealed` có thể bao phủ mọi descendant |
| “`MatchException` đồng nghĩa `NullPointerException`.” | Hai exception khác nhau; `null` selector thiếu `case null` gây NPE |
| “Thêm `case null` là đủ cho mọi thay đổi hierarchy.” | `case null` chỉ xử lý null, không xử lý subtype mới |
| “Không crash nghĩa là logic vẫn đúng.” | Fallback chung có thể âm thầm xử lý sai subtype mới |

## Kết luận

**Sealed hierarchy** tăng an toàn kiểu bằng cách cho phép compiler chứng minh `switch` đã exhaustive, nhưng sự bảo đảm đó phụ thuộc vào **phiên bản của hierarchy tại thời điểm biên dịch**. Khi hierarchy thay đổi:

- **Biên dịch lại** với subtype mới có thể tạo lỗi **non-exhaustive** và buộc bạn cập nhật case.
- **Giữ client binary cũ nhưng triển khai thư viện mới** có thể dẫn đến **`MatchException`** nếu runtime nhận subtype mới không có nhánh tương ứng.
- **Thêm `default`** có thể cung cấp fallback nhưng cũng có thể che việc thiếu case; dùng nó theo chính sách nghiệp vụ, không chỉ để mã biên dịch.
- **Dùng nhánh `non-sealed`** khi thực sự cần extension point; bao phủ nhánh rộng và kiểm tra hành vi với subtype mới.

Hãy kết hợp **rebuild toàn bộ consumer**, test nhiều tổ hợp version, xử lý từng subtype có chủ đích và quan sát runtime để tránh biến một thay đổi kiểu “binary compatible” thành lỗi ứng dụng.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): exhaustive switch với sealed types và tình huống `MatchException` khi hierarchy tiến hóa.
- [Oracle Java 21 — MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html): định nghĩa và các trường hợp separate compilation gây lỗi.
- [JLS Java 21 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html): quy tắc về thay đổi `permits`, binary compatibility và migration compatibility.
- [Oracle Java 21 — Sealed Classes](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html): `sealed`, `final`, `non-sealed` và giới hạn kế thừa.
