# Qualified enum constant trong Java 21

## 1. Khái niệm và mục tiêu

Trong Java, một kiểu `enum` định nghĩa một tập giá trị hữu hạn, mỗi giá trị là **enum constant**. Chẳng hạn:

```java
enum Phase {
    NEW, RUNNING, DONE
}
```

Các giá trị có tên đầy đủ là `Phase.NEW`, `Phase.RUNNING`, `Phase.DONE`. Khi viết cả **tên kiểu enum** và **tên hằng**, ta gọi đó là **qualified enum constant**:

```java
Phase.NEW
```

Trong một nhãn `case`:

```java
case Phase.NEW -> "new";
```

nhãn này chọn đúng hằng `NEW` của enum `Phase`, không phải bất kỳ chuỗi hoặc đối tượng nào có tên tương tự.

**Điểm mới đáng nhớ của Java 21:** pattern matching for `switch` (JEP 441) cho phép dùng **qualified enum constants** trong case labels, kể cả khi kiểu tĩnh của biểu thức selector không phải chính enum đó, miễn là hằng enum có kiểu phù hợp với selector. Nhờ vậy một switch trên `Object` hoặc interface có thể nhận các hằng thuộc nhiều enum khác nhau.

Nội dung bài tập trung vào cú pháp, lý do cần qualifier, trường hợp hợp lệ/không hợp lệ, cách phối hợp với type patterns, thứ tự case, tính bao phủ, `null` và ví dụ Java 21 có thể chạy ngay.

**Phiên bản:** dùng **JDK 21+** với cú pháp Java 21 chuẩn, không dùng preview. Các phiên bản Java 17 và cũ hơn có quy tắc khác cho nhãn enum trong switch truyền thống; cần phân biệt khi bảo trì mã.

## 2. Qualified và unqualified: hai cách viết một enum constant

Với enum `Phase`:

- `NEW` là **unqualified enum constant name** — chỉ tên hằng.
- `Phase.NEW` là **qualified enum constant name** — tên kiểu đi kèm tên hằng.

Khi selector có kiểu `Phase`, switch cổ điển thường viết:

```java
static String phaseName(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
    };
}
```

Đây là đoạn minh họa đặt trong class chứa khai báo `Phase`; cú pháp `case NEW` hợp lệ từ các phiên bản Java trước Java 21. Vì selector đã có kiểu tĩnh `Phase`, compiler biết hằng `NEW` thuộc enum nào.

Từ **Java 21**, ta có thể viết rõ tên enum trong cùng bài toán:

```java
static String phaseName21(Phase phase) {
    return switch (phase) {
        case Phase.NEW -> "new";
        case Phase.RUNNING -> "running";
        case Phase.DONE -> "done";
    };
}
```

Cả hai cách trả về cùng kết quả đối với các giá trị `Phase`. Java 21 chấp nhận dạng qualified trong switch trên enum, và còn hỗ trợ nó với selector kiểu rộng hơn.

**Quan trọng về tương thích:** trong Java 17, `case Phase.NEW` trong switch có selector `Phase` bị compiler từ chối với thông báo yêu cầu *unqualified name* của hằng enum. Nếu đang phải biên dịch bằng Java 17, dùng `case NEW` trong switch truyền thống trên chính enum đó. Đừng nhầm cú pháp Java 21 ổn định với cú pháp được hỗ trợ ở mọi phiên bản.

## 3. Vì sao cần qualified constant khi selector là Object?

Xét trường hợp chuyển dữ liệu qua một API nhận `Object`:

```java
Object event = Phase.NEW;
```

Nếu viết `switch (event)` trong Java 21, compiler chỉ biết kiểu tĩnh của selector là `Object`; nó không có một enum duy nhất để suy ra `NEW` thuộc kiểu nào.

Cách viết đúng cho một enum constant là:

```java
static String inspect(Object event) {
    return switch (event) {
        case Phase.NEW -> "new phase";
        case Phase.DONE -> "finished phase";
        case Phase phase -> "another phase: " + phase;
        default -> "not a Phase";
    };
}
```

Ý nghĩa:

1. `case Phase.NEW`: chỉ khớp đúng đối tượng hằng `Phase.NEW`.
2. `case Phase.DONE`: chỉ khớp hằng `Phase.DONE`.
3. `case Phase phase`: đây là một **type pattern**, khớp các giá trị `Phase` còn lại và khai báo biến `phase` có kiểu tĩnh `Phase`.
4. `default`: xử lý các đối tượng không khớp ba nhánh trước, trừ quy tắc `null` cần xét riêng.

Với `inspect(Phase.RUNNING)`, kết quả là `"another phase: RUNNING"`. Với `inspect("NEW")`, kết quả là `"not a Phase"` — chuỗi `"NEW"` không tự được chuyển thành `Phase.NEW`.

Điểm cần hiểu: **qualified enum constant không kiểm tra “tên trùng khớp”** mà kiểm tra một giá trị enum cụ thể. Mỗi enum constant là một đối tượng duy nhất của enum tương ứng. Hai enum cùng có hằng tên `NEW` vẫn sở hữu hai đối tượng khác nhau.

## 4. Hai enum có cùng tên hằng: trường hợp Java 21 thể hiện rõ lợi ích

Hãy mô hình hóa hai quy trình độc lập:

```java
sealed interface TaskState permits Download, Upload {}

enum Download implements TaskState {
    NEW, RUNNING, DONE
}

enum Upload implements TaskState {
    NEW, RUNNING, FAILED
}
```

Ở đây, `Download.NEW` và `Upload.NEW` đều có tên `NEW` nhưng thuộc **hai enum riêng biệt**. Tương tự, `Download.RUNNING` và `Upload.RUNNING` là hai giá trị khác nhau. Nhờ qualified enum constants, switch trên interface `TaskState` có thể phân biệt chính xác:

```java
static String stateName(TaskState value) {
    return switch (value) {
        case Download.NEW -> "download created";
        case Upload.NEW -> "upload created";
        case Download.RUNNING, Upload.RUNNING -> "running";
        case Download.DONE -> "download complete";
        case Upload.FAILED -> "upload failed";
        case null -> "missing";
    };
}
```

Đây là đoạn minh họa trong class có các khai báo enum/interface ở trên. Các nhãn `case Download.NEW` và `case Upload.NEW` hoàn toàn tách biệt. Một nhánh gồm **hai hằng** ngăn cách bởi dấu phẩy:

```java
case Download.RUNNING, Upload.RUNNING -> "running";
```

cho phép nhiều giá trị enum cùng dẫn đến một kết quả, kể cả hai giá trị thuộc hai enum khác nhau, miễn nhãn hợp lệ với kiểu selector. Khác với type pattern, các enum constant labels này **không** tạo ra biến binding.

Đây là một trong những lợi ích thiết thực của Java 21: viết switch trực tiếp trên interface chung, không phải ép enum về chuỗi rồi so tên hằng.

## 5. Kiểu tĩnh của selector quyết định tính hợp lệ

Qualified enum constant trong case vẫn phải đáp ứng kiểm tra kiểu của Java. Nó không được đặt tùy tiện vào mọi switch.

| Kiểu tĩnh của selector | Nhãn case | Kết luận Java 21 |
| --- | --- | --- |
| `Phase` | `case NEW` | Hợp lệ, unqualified enum constant trong switch trên chính enum |
| `Phase` | `case Phase.NEW` | Hợp lệ, qualified enum constant |
| `Object` | `case Phase.NEW` | Hợp lệ, selector có thể chứa giá trị `Phase` |
| `TaskState` | `case Download.NEW` | Hợp lệ, `Download` triển khai `TaskState` |
| `TaskState` | `case Upload.FAILED` | Hợp lệ, `Upload` triển khai `TaskState` |
| `String` | `case Phase.NEW` | Không hợp lệ: kiểu `Phase` không tương thích với selector `String` |
| `Download` | `case Upload.NEW` | Không hợp lệ: hằng `Upload` không thể là giá trị `Download` |

Trường hợp lỗi kiểu rõ nhất:

```java
// Không biên dịch được: switch trên String, nhưng case là hằng enum.
// static String wrong(String text) {
//     return switch (text) {
//         case Phase.NEW -> "new";
//         default -> "other";
//     };
// }
```

Đây là **lỗi compile-time**, không phải một nhánh hợp lệ nhưng chỉ không được gọi ở runtime. Selector kiểu `String` không thể chứa một hằng `Phase`. Nếu đầu vào của ứng dụng là văn bản `"NEW"`, hãy xử lý nó như `String` hoặc chuyển đổi có kiểm tra thành enum trước khi switch.

Khi selector kiểu `Object` hoặc interface chung, qualifier giúp compiler biết enum cần so khớp; nhưng điều kiện tương thích kiểu vẫn được kiểm tra.

## 6. Ví dụ Java 21 hoàn chỉnh: enum constants thuộc hai quy trình

Lưu mã sau thành **QualifiedEnumConstant21Demo.java**:

```java
public class QualifiedEnumConstant21Demo {
    sealed interface TaskState permits Download, Upload {}

    enum Download implements TaskState {
        NEW, RUNNING, DONE
    }

    enum Upload implements TaskState {
        NEW, RUNNING, FAILED
    }

    static String task(TaskState value) {
        return switch (value) {
            case null -> "missing";
            case Download.NEW -> "download:new";
            case Upload.NEW -> "upload:new";
            case Download.RUNNING, Upload.RUNNING -> "running";
            case Download.DONE -> "download:done";
            case Upload.FAILED -> "upload:failed";
        };
    }

    static String generic(Object value) {
        return switch (value) {
            case null -> "null";
            case Download.NEW -> "start-download";
            case Upload.NEW -> "start-upload";
            case Download d -> "download:" + d.name();
            case Upload u -> "upload:" + u.name();
            default -> "other";
        };
    }

    static String onlyDownload(Download value) {
        return switch (value) {
            case Download.NEW -> "new";
            case RUNNING -> "running";
            case DONE -> "done";
        };
    }

    public static void main(String[] args) {
        System.out.println(task(Download.NEW));
        System.out.println(task(Upload.NEW));
        System.out.println(task(Download.RUNNING));
        System.out.println(task(Upload.RUNNING));
        System.out.println(task(Download.DONE));
        System.out.println(task(Upload.FAILED));
        System.out.println(task(null));

        System.out.println(generic(Download.NEW));
        System.out.println(generic(Upload.NEW));
        System.out.println(generic(Upload.FAILED));
        System.out.println(generic("NEW"));
        System.out.println(generic(null));

        System.out.println(onlyDownload(Download.DONE));
    }
}
```

Biên dịch và chạy:

```bash
javac QualifiedEnumConstant21Demo.java
java QualifiedEnumConstant21Demo
```

**Đầu ra chính xác:**

```text
download:new
upload:new
running
running
download:done
upload:failed
missing
start-download
start-upload
upload:FAILED
other
null
done
```

### Giải thích chương trình

- `TaskState` là **sealed interface**. Chỉ hai enum `Download` và `Upload` được phép trực tiếp triển khai interface này.
- `task(TaskState value)` dùng qualified enum constants để liệt kê **toàn bộ sáu hằng** thuộc hai enum. Nhánh `case null` xử lý dữ liệu vắng mặt. Switch expression **không cần `default`** vì compiler Java 21 xác định được các trường hợp enum trong hierarchy này đã được bao phủ.
- `case Download.RUNNING, Upload.RUNNING` chứng minh hai enum constants từ những enum khác nhau có thể đi chung một nhánh.
- `generic(Object value)` nhận kiểu rộng `Object`. Hai hằng `NEW` được kiểm tra riêng trước khi type patterns `Download d` và `Upload u` xử lý các hằng còn lại.
- `generic(Upload.FAILED)` vào `case Upload u` nên trả `"upload:FAILED"` bằng phương thức `name()`; nó không phải chuỗi trả về từ nhánh `task`.
- `generic("NEW")` trả `"other"` vì `String` không phải enum. `generic(null)` trả `"null"` nhờ `case null`.
- `onlyDownload(Download value)` chứng minh Java 21 cho phép **kết hợp nhãn qualified và unqualified** khi selector đã là enum `Download`.
- Hai enum cùng có tên `NEW` nhưng không bao giờ bị nhầm lẫn, vì mỗi nhãn đầy đủ đều chỉ rõ lớp enum sở hữu hằng.

Khi viết chương trình thật, khai báo `sealed interface` và các enum có thể là các kiểu top-level (đặt trong file riêng hoặc package phù hợp); chúng được lồng trong class ở ví dụ này chỉ để có một tệp tự chạy.

## 7. Exhaustiveness: liệt kê hằng enum để bao phủ các giá trị có thể có

**Exhaustiveness** nghĩa là compiler chứng minh switch có nhánh cho mọi giá trị hợp lệ của selector theo quy tắc ngôn ngữ.

### Switch trên một enum

```java
static String name(Download value) {
    return switch (value) {
        case Download.NEW -> "N";
        case Download.RUNNING -> "R";
        case Download.DONE -> "D";
    };
}
```

Vì `Download` được khai báo với ba hằng `NEW`, `RUNNING`, `DONE` và cả ba có nhãn, switch expression đủ bao phủ (đối với giá trị khác `null`) nên không cần `default`.

### Switch trên sealed interface được triển khai bởi enum

Trong chương trình chính, `TaskState` chỉ có hai enum được phép triển khai và hai enum tổng cộng có sáu hằng. Compiler Java 21 có thể xét **tập hằng của các enum được permits** để xác định tính bao phủ trong ví dụ:

```java
return switch (value) {
    case null -> "missing";
    case Download.NEW -> "download:new";
    case Upload.NEW -> "upload:new";
    case Download.RUNNING, Upload.RUNNING -> "running";
    case Download.DONE -> "download:done";
    case Upload.FAILED -> "upload:failed";
};
```

Không có `default` mà vẫn biên dịch. Nếu bỏ `case Upload.FAILED` và không thêm nhánh khác bao phủ giá trị này, switch expression sẽ thiếu exhaustive theo loại selector đó.

### Selector rộng như Object

Nếu `switch` nhận `Object`, không thể chỉ liệt kê các hằng của hai enum rồi xem như đã xử lý mọi đối tượng. Ngoài hai enum, còn có `String`, `Integer`, các class khác... Vì vậy trong `generic(Object value)`, nhánh `default` được dùng để bao phủ những giá trị không phải hai enum.

**Chú ý khi thay đổi kiểu:** nếu bổ sung enum constant mới hay thay đổi sealed hierarchy, biên dịch lại switch để compiler kiểm tra tính bao phủ. Không nên thêm `default` một cách máy móc nếu muốn compiler buộc cập nhật khi mô hình trạng thái thay đổi.

## 8. Dominance và nhãn trùng lặp: đặt hằng cụ thể trước type pattern

Qualified enum constant là một giá trị **cụ thể**. Type pattern như `case Download d` lại bao phủ **mọi hằng Download** khác null. Vì thế thứ tự case có ý nghĩa.

Đoạn sau **sai**:

```java
// Không biên dịch được: Download.NEW bị type pattern trước chi phối.
// static String wrong(Object value) {
//     return switch (value) {
//         case Download d -> "any Download";
//         case Download.NEW -> "specific new"; // Dominated
//         default -> "other";
//     };
// }
```

Nhánh `case Download d` đứng trước sẽ nhận cả `Download.NEW`, khiến case phía sau không thể được chọn. Compiler Java 21 phát hiện **dominance** và từ chối nhãn bị che.

Sửa bằng cách đổi thứ tự:

```java
static String right(Object value) {
    return switch (value) {
        case Download.NEW -> "specific new";
        case Download d -> "another Download";
        default -> "other";
    };
}
```

Tương tự, nếu viết cả `case NEW` và `case Download.NEW` trong cùng một switch có selector kiểu `Download` như hai nhãn riêng, hai nhãn đều chỉ **một hằng giống nhau**. Compiler báo **duplicate case label**. Thêm qualifier không tạo một constant mới.

Cần phân biệt:

| Vấn đề | Ví dụ | Lý do |
| --- | --- | --- |
| Nhãn trùng | `case NEW` và `case Download.NEW` trong cùng switch trên `Download` | Cả hai biểu thị hằng `Download.NEW` |
| Dominance | `case Download d` trước `case Download.NEW` | Type pattern đã bao phủ hằng cụ thể |
| Không exhaustive | Chỉ có `case Download.NEW` khi selector là `Object` | Các kiểu/giá trị khác chưa được xử lý |
| Không tương thích kiểu | `case Download.NEW` với selector kiểu `String` | Hằng enum không thể là một `String` |
| Lỗi `null` | Không có `case null` nhưng selector nhận `null` | Switch trên tham chiếu có thể ném `NullPointerException` |

Với nhiều nhãn `case`, đặt nhánh xử lý hằng đặc biệt trước type pattern tổng quát và tránh khai báo lại cùng hằng.

## 9. Qualified enum constant khác với pattern và guard `when`

So sánh ba dạng:

```java
// Một hằng chính xác:
case Download.NEW -> "new";

// Mọi hằng thuộc Download, đồng thời tạo biến pattern:
case Download d -> "download:" + d.name();

// Chỉ một số giá trị Download thỏa điều kiện bổ sung:
case Download d when d == Download.RUNNING -> "downloading";
```

- `case Download.NEW` là **constant label**, không khai báo pattern variable.
- `case Download d` là **type pattern** và tạo biến `d` kiểu `Download` khi khớp.
- `case Download d when ...` là **guarded pattern label**: sau khi type pattern khớp, guard boolean được đánh giá.

Đừng viết trực tiếp:

```java
// Không đúng cú pháp guard cho enum constant trong Java 21:
// case Download.NEW when enabled -> "start now";
```

Nếu muốn xử lý hằng `Download.NEW` chỉ khi một điều kiện động đúng, có thể dùng type pattern cùng guard, rồi fallback bằng constant label:

```java
static String start(Object value, boolean enabled) {
    return switch (value) {
        case Download d when d == Download.NEW && enabled ->
                "start enabled";
        case Download.NEW -> "start disabled";
        case Download d -> "other download";
        default -> "other";
    };
}
```

Đây là đoạn minh họa đặt trong class có khai báo `Download`. Guard không tạo một hằng enum khác và không kiểm tra lại selector từ đầu. Với `Download.NEW` và `enabled == true`, nhánh guard được chọn; khi false, nhánh `case Download.NEW` phía sau được chọn.

Nếu điều kiện chỉ xoay quanh hằng cụ thể và không cần một pattern, có thể dùng `case Download.NEW -> enabled ? "start enabled" : "start disabled";` để giữ nhãn đơn giản.

## 10. Xử lý null: hằng enum không thể là null

Enum constant là một đối tượng hằng, nên không có hằng enum `Download.null`. Khi selector có kiểu tham chiếu, giá trị `null` là một trường hợp riêng:

```java
static String optional(Object value) {
    return switch (value) {
        case null -> "missing";
        case Download.NEW -> "new";
        default -> "other";
    };
}
```

Trong Java 21, `case null` xử lý selector null. Nếu thiếu nhánh này, `default` không tự bắt null; phép switch trên tham chiếu có thể ném `NullPointerException` trước khi thực hiện nhánh khác.

Java 21 còn cho phép kết hợp đặc biệt `case null, default -> ...` khi cùng muốn xử lý null và mọi giá trị còn lại; nhưng khi null có ý nghĩa nghiệp vụ riêng, nhãn riêng `case null` giúp code rõ ràng hơn.

Một switch expression có thể **exhaustive theo kiểu** mà vẫn ném `NullPointerException` khi selector là null. Ví dụ `onlyDownload(null)` trong chương trình chính không có `case null` và sẽ ném NPE. Đó là hành vi cần hiểu, không phải dấu hiệu rằng thiếu một hằng enum nào đó.

## 11. Khi nào sử dụng switch enum, khi nào dùng nhiều enum trong một switch?

Ưu tiên cách đơn giản nhất phù hợp với kiểu dữ liệu.

**Chỉ một enum:** Nếu phương thức nhận `Download`, switch trực tiếp trên `Download` và liệt kê các hằng. Có thể dùng qualified names để nhất quán với Java 21, nhưng unqualified `case NEW` vẫn dễ đọc và tương thích phiên bản cũ hơn.

**Nhiều enum cùng vai trò:** Nếu nghiệp vụ có hai enum khác nhau nhưng cùng triển khai một interface, Java 21 cho phép switch trên interface và dùng `Download.NEW`, `Upload.NEW` để xử lý đúng từng giá trị. Đây là trường hợp biểu đạt rõ ràng nhất giá trị của qualified constants.

**Đầu vào kiểu Object:** Khi thật sự xử lý dữ liệu nhiều loại, switch trên `Object` và dùng các enum-qualified case labels, type patterns và `default` thích hợp. Nhưng nếu thực chất API chỉ cho phép `TaskState`, nên khai báo tham số kiểu `TaskState` thay vì `Object` để nhận thêm kiểm tra compile-time.

**Đầu vào từ chuỗi, JSON hoặc file:** Parse/validate thành enum rồi mới switch. Không dùng `case Download.NEW` để “tự động parse” một chuỗi `"NEW"`.

Ví dụ chuyển chuỗi:

```java
static Download parseDownload(String text) {
    return Download.valueOf(text);
}
```

`valueOf` chỉ chấp nhận tên hằng chính xác của enum, phân biệt chữ hoa/thường. Với chuỗi không hợp lệ, phương thức ném `IllegalArgumentException`; với `null`, nó ném `NullPointerException`. Một API nhận dữ liệu ngoài cần xác định cách xử lý các lỗi này hoặc trả về kết quả lỗi có kiểm soát.

Đối với hệ thống nhiều loại trạng thái, cân nhắc giữ rõ ngữ nghĩa ở type system — `sealed interface TaskState` cùng hai enum — hơn là chuyển tất cả trạng thái thành chuỗi và so sánh thủ công.

## 12. Lỗi thường gặp và cách sửa

| Cách hiểu hoặc mã sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `case Download.NEW` và yêu cầu biên dịch Java 17. | Quy tắc qualified enum case của Java 21 chưa có trong Java 17 ổn định. | Dùng JDK 21+, hoặc `case NEW` với selector kiểu `Download` trên Java 17. |
| Viết `case NEW` trong switch trên `Object` rồi mong compiler chọn đúng enum. | `Object` không xác định enum nào có hằng `NEW`. | Viết rõ `case Download.NEW` hoặc `case Upload.NEW`. |
| Cho rằng hai enum hằng `NEW` là cùng một giá trị. | `Download.NEW` và `Upload.NEW` thuộc hai enum khác nhau. | Giữ qualifier và phân biệt đường xử lý theo loại enum. |
| Nhầm `case Download.NEW` với `case Download d`. | Một bên là hằng cụ thể; một bên match toàn bộ kiểu và khai báo biến. | Chọn label theo phạm vi giá trị cần xử lý. |
| Đặt `case Download d` trước `case Download.NEW`. | Type pattern bao phủ hằng cụ thể, gây dominance. | Đặt hằng chuyên biệt trước type pattern tổng quát. |
| Có cả `case NEW` và `case Download.NEW` cho một hằng trong cùng switch. | Duplicate case label. | Chỉ giữ một nhãn cho hằng đó. |
| Đặt `case Download.NEW` trong switch trên `String`. | Kiểu selector và enum constant không tương thích. | Chuyển đầu vào thành enum đúng kiểu hoặc switch trên String. |
| Nghĩ mọi switch có enum constants đều exhaustive. | Có thể thiếu hằng hoặc selector thuộc kiểu rộng hơn. | Xét toàn bộ tập giá trị theo kiểu tĩnh selector và bổ sung nhánh phù hợp. |
| Viết `case Download.NEW when enabled`. | `when` dùng với guarded pattern, không gắn trực tiếp vào constant label kiểu này. | Dùng `case Download d when d == Download.NEW && enabled` hoặc điều kiện trong thân case. |
| Cho rằng `default` thay được `case null`. | Quy tắc switch trên tham chiếu Java 21 xử lý null riêng. | Có `case null` khi muốn nhận null. |
| So `"NEW"` với enum constant trong switch. | Chuỗi không phải hằng enum. | Parse/validate bằng `valueOf` hoặc API phù hợp. |

## 13. Bài tập tự luyện và đáp án

### Bài 1 — Đoán nhánh được chọn

Với khai báo `Download`, `Upload` và `TaskState` từ chương trình chính:

```java
TaskState a = Download.NEW;
TaskState b = Upload.NEW;
TaskState c = Upload.FAILED;
```

Nếu gọi `task(a)`, `task(b)` và `task(c)`, kết quả lần lượt là gì?

**Đáp án:** `"download:new"`, `"upload:new"`, `"upload:failed"`. Không phải cứ cùng tên `NEW` là có thể dùng một nhãn unqualified chung khi selector là `TaskState`.

### Bài 2 — Nhận diện lỗi compile-time

Cho:

```java
static String bad(Object value) {
    return switch (value) {
        case Download d -> "any download";
        case Download.NEW -> "just new";
        default -> "other";
    };
}
```

**Đáp án:** nhánh `case Download.NEW` bị **dominated** vì mọi hằng `Download` đã được nhánh `case Download d` xử lý. Đưa `Download.NEW` lên trước nếu cần kết quả chuyên biệt.

### Bài 3 — Kiểm tra exhaustiveness

Giả sử `TaskState` chỉ cho phép hai enum `Download { NEW, RUNNING, DONE }` và `Upload { NEW, RUNNING, FAILED }`. Switch expression chỉ liệt kê:

```java
return switch (state) {
    case Download.NEW -> "download-new";
    case Download.RUNNING -> "download-running";
    case Download.DONE -> "download-done";
    case Upload.NEW -> "upload-new";
    case Upload.RUNNING -> "upload-running";
};
```

**Đáp án:** còn thiếu `Upload.FAILED`. Với selector kiểu `TaskState` trong mô hình này, compiler không chấp nhận switch expression thiếu tính exhaustive. Bổ sung `case Upload.FAILED -> "upload-failed";` hoặc một nhánh khác thật sự bao phủ trường hợp đó.

### Bài 4 — Gộp các hằng cùng trạng thái

Hãy viết một nhánh `case` xử lý `Download.RUNNING` và `Upload.RUNNING` cùng trả về `"active"`.

**Đáp án:**

```java
case Download.RUNNING, Upload.RUNNING -> "active";
```

Cả hai hằng phải tương thích với kiểu selector của switch; ví dụ selector `TaskState` hoặc `Object` là phù hợp.

### Bài 5 — Chọn phiên bản Java đúng

Trong Java 17, muốn switch trên một biến `Download value`, dùng `case NEW` hay `case Download.NEW`?

**Đáp án:** dùng `case NEW` (unqualified) trong switch enum truyền thống. Trong Java 21, cả hai cách đều có thể được dùng với selector `Download`. Khi selector là `TaskState` hay `Object` ở Java 21, qualified name xác định rõ enum cần kiểm tra.

### Bài 6 — Null và chuỗi

Tại sao `generic(null)` trả `"null"` nhưng `generic("NEW")` trả `"other"`?

**Đáp án:** `generic(null)` có nhánh `case null`; chuỗi `"NEW"` không phải `Download.NEW` hoặc `Upload.NEW` và không khớp các type patterns của hai enum, vì vậy dùng `default`.

## 14. Tóm tắt ghi nhớ

**Qualified enum constant** là tên hằng có đầy đủ kiểu enum, ví dụ `Download.NEW` hoặc `Upload.NEW`. Java 21 cho phép dùng dạng này trong case label của pattern switch để lựa chọn chính xác hằng enum, ngay cả khi selector có kiểu tĩnh là interface hoặc `Object`.

Những điểm cần thuộc:

1. **Java 21 mở rộng cú pháp case enum:** với selector đã có kiểu enum, `case NEW` và `case Download.NEW` đều hợp lệ; Java 17 yêu cầu dạng unqualified trong switch enum cổ điển.
2. **Qualifier phân biệt danh tính:** `Download.NEW` không phải `Upload.NEW`, và không phải chuỗi `"NEW"`.
3. **Constant khác pattern:** `case Download.NEW` chỉ khớp một hằng; `case Download d` khớp mọi hằng `Download` khác null và tạo biến `d`.
4. **Thứ tự và kiểu đều quan trọng:** hằng chuyên biệt nên đứng trước pattern tổng quát; enum constant phải tương thích kiểu selector.
5. **Không quên tính bao phủ và null:** switch expression cần exhaustive; `case null` xử lý giá trị vắng mặt khi cần, `default` không tự thay thế null.

### Tài liệu chính thức

- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification — switch statement (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification — switch expression (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
