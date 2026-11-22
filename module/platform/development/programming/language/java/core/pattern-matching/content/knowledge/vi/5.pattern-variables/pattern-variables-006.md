# Pattern variable trong block lồng nhau (Java 17+)

## 1. Bài toán: biến pattern tồn tại đến đâu khi có nhiều lớp ngoặc nhọn?

Trong Java, một **pattern variable** là biến được khai báo trong mẫu so khớp (pattern). Với type pattern của `instanceof`, cách viết thông dụng là:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length());
}
```

Biểu thức `value instanceof String text` vừa kiểm tra giá trị runtime có phải `String` hay không, vừa ràng buộc đối tượng đã khớp với biến `text` có kiểu `String`. Mã trong nhánh `if` có thể gọi `text.length()` mà không cần ép kiểu.

Khi xuất hiện **block lồng nhau** — các cặp `{ ... }` bên trong `if`, `else`, vòng lặp, hoặc các block độc lập — có hai loại quy tắc cùng quyết định nơi dùng được `text`:

1. **Phạm vi cú pháp của block:** một biến được khai báo trong block con không tự nhiên xuất hiện bên ngoài block đó.
2. **Phạm vi theo luồng điều khiển (flow scoping):** biến pattern chỉ có mặt ở những vị trí mà trình biên dịch chứng minh phép so khớp đã thành công. Vì vậy, đôi khi biến pattern còn dùng được sau một câu lệnh `if` nếu nhánh không khớp đã thoát bằng `return` hoặc `throw`.

Điểm quan trọng: **block lồng nhau không tự động làm mất biến pattern có sẵn từ block cha**. Nếu mẫu đã khớp và biến còn trong phạm vi, các block con thông thường vẫn truy cập được. Ngược lại, các dấu ngoặc nhọn không thể khiến một biến pattern chưa khớp trở nên hợp lệ.

Các quy tắc dưới đây áp dụng cho **type pattern của `instanceof` trên Java 17+**. Pattern matching cho `instanceof` được chuẩn hóa từ Java 16 theo JEP 394; không cần bật preview trên Java 17.

## 2. Mô hình tư duy: kết hợp phạm vi block và phép khớp chắc chắn

Hãy xem cấu trúc nhiều tầng:

```java
Object value = "  Java  ";

if (value instanceof String text) {
    // Tầng 1: đã khớp String, dùng được text.
    if (!text.isBlank()) {
        // Tầng 2: vẫn có text.
        {
            // Tầng 3: block độc lập cũng đọc được text.
            System.out.println(text.strip());
        }
    }
}
```

Trong mọi tầng nằm trong nhánh `if` đầu tiên, điều kiện `value instanceof String text` đã đúng. Không cần kiểm tra lại kiểu ở mỗi block.

Cùng lúc, phạm vi của một biến cục bộ thông thường được khai báo ở block trong chỉ kéo dài trong block đó:

```java
if (value instanceof String text) {
    {
        int length = text.length();
        System.out.println(length);
    }

    System.out.println(text);   // Hợp lệ: text vẫn thuộc nhánh đã khớp.
    // System.out.println(length); // Lỗi: length khai báo ở block con.
}
```

Từ ví dụ này, cần phân biệt **nguồn gốc của hai biến**:

- `text` được giới thiệu qua type pattern trong điều kiện `if`, nên hợp lệ tại các vị trí của nhánh `if` mà phép khớp đã được bảo đảm.
- `length` là biến cục bộ thường được khai báo bên trong block con, nên không được truy cập từ block cha sau khi block con kết thúc.

Không nên suy ra phạm vi chỉ dựa vào “biến nằm trong mấy cặp ngoặc nhọn”. Hãy xác định **biến khai báo ở đâu**, và đối với biến pattern, **đường đi đến vị trí sử dụng có bắt buộc phải khớp không**.

## 3. Pattern variable trong `if` lồng `if`

### 3.1. Pattern ở `if` ngoài, sử dụng ở `if` trong

```java
static String description(Object input) {
    if (input instanceof String text) {
        if (!text.isBlank()) {
            if (text.length() >= 4) {
                return "Long: " + text.strip();
            }
            return "Short: " + text.strip();
        }
        return "Blank";
    }
    return "Not a string";
}
```

Ở ba tầng điều kiện, `text` đã được xác nhận là `String` từ tầng ngoài. Cả `isBlank()`, `length()` và `strip()` đều là lời gọi hợp lệ. Không có lệnh ép kiểu `(String) input` nào cần thiết.

Với `input = " Java "`, kết quả là `"Long: Java"`. Với `input = "a"`, kết quả là `"Short: a"`; với `input = null`, kết quả là `"Not a string"`.

### 3.2. Pattern chỉ được khai báo ở `if` trong

```java
static String firstText(Object input) {
    if (input instanceof java.util.List<?> items) {
        if (!items.isEmpty()) {
            Object first = items.get(0);

            if (first instanceof String text) {
                return text.strip();
            }

            // Không được dùng text ở đây:
            // first có thể không phải String.
        }

        // Không được dùng text ở đây:
        // block kiểm tra first đã kết thúc.
        return "No matching first element";
    }
    return "Not a list";
}
```

`items` được giới thiệu ở tầng ngoài, nên có thể dùng trong mọi block con của nhánh đã khớp. `text` được giới thiệu trong một điều kiện bên trong, nên chỉ dùng tại những vị trí mà **`first instanceof String text` đúng**.

Nếu `input` là danh sách có phần tử đầu là `Integer`, nhánh `if (first instanceof String text)` không chạy; không có `text` nào được tạo ra cho đường đi đó.

### 3.3. Nhiều pattern ở các tầng khác nhau

```java
static String repeat(Object left, Object right) {
    if (left instanceof String text) {
        if (right instanceof Integer times) {
            if (times > 0) {
                return text.repeat(times);
            }
        }
        return "Not repeated";
    }
    return "Left is not text";
}
```

Trong block sâu nhất, **cả `text` và `times`** đều có hiệu lực: đến đó bắt buộc `left` đã khớp `String` và `right` đã khớp `Integer`. Ở đoạn `return "Not repeated"` sau `if` trong, `text` vẫn hợp lệ, nhưng không thể mặc nhiên dùng `times`, vì `right` có thể không phải `Integer`.

Quy tắc này tạo nên một cách viết rõ ràng khi cần kiểm tra từng bước: các biến pattern của tầng ngoài vẫn sẵn có ở tầng trong; biến pattern của tầng trong chỉ được dùng khi điều kiện tương ứng được bảo đảm.

## 4. Nhánh `else` trong các block lồng nhau

Một hiểu nhầm thường gặp là: “Đã khai báo biến pattern trong điều kiện `if`, vậy `else` cùng cặp `if` cũng biết biến đó.” Điều này **không đúng** với type pattern dương.

```java
if (input instanceof String text) {
    System.out.println(text.length()); // Hợp lệ.
} else {
    // System.out.println(text); // LỖI BIÊN DỊCH.
    System.out.println("Not text");
}
```

Nhánh `else` chạy khi `instanceof` trả về `false`. Biến `text` chưa khớp nên không được dùng ở đó.

Tương tự, trong block lồng nhau:

```java
if (input instanceof java.util.List<?> items) {
    if (items.get(0) instanceof String first) {
        System.out.println(first.length());
    } else {
        // first không có trong nhánh này.
        System.out.println("First element is not text");
    }

    // items hợp lệ ở đây; first không được bảo đảm.
}
```

Đoạn này là **minh họa phạm vi**, giả định `items` không rỗng; gọi `items.get(0)` với danh sách rỗng sẽ gây `IndexOutOfBoundsException`. Khi viết mã thực tế, hãy kiểm tra `!items.isEmpty()` trước khi truy cập phần tử đầu, như trong ví dụ hoàn chỉnh ở phần sau.

### Dùng lại tên pattern trong `else if`

Hai nhánh loại trừ nhau có thể dùng cùng một tên biến pattern nếu phạm vi không chồng lấn:

```java
static String label(Object value) {
    if (value instanceof String item) {
        return "TEXT:" + item;
    } else if (value instanceof Integer item) {
        return "NUMBER:" + item;
    } else {
        return "OTHER";
    }
}
```

Hai biến `item` ở đây có **hai khai báo khác nhau** và các phạm vi không giao nhau. Trong nhánh đầu, `item` là `String`; trong nhánh thứ hai, `item` là `Integer`. Mỗi nhánh chỉ được dùng biến mà pattern của chính nhánh đó đã khớp.

Tuy hợp lệ, nếu nhiều nhánh lồng sâu, đặt tên riêng như `text`, `number` thường giúp mã dễ đọc hơn.

## 5. Block lồng nhau không làm biến pattern tự thoát khỏi phạm vi cha

Xem đoạn:

```java
if (input instanceof String text) {
    {
        String normalized = text.strip();
        System.out.println(normalized);
    }

    // text vẫn hợp lệ trong nhánh if.
    System.out.println(text.length());

    // normalized đã hết phạm vi.
    // System.out.println(normalized); // LỖI BIÊN DỊCH.
}

// text không được bảo đảm ở đây.
// System.out.println(text); // LỖI BIÊN DỊCH.
```

Có ba cấp cần phân biệt:

1. **Tầng phương thức:** biến `input` có mặt trong vùng khai báo của nó.
2. **Nhánh `if` đã khớp:** biến `text` có mặt trong nhánh này, kể cả các block con.
3. **Block độc lập bên trong:** biến `normalized` chỉ có mặt trong block khai báo nó.

Các block con không mở rộng phạm vi biến `normalized` ra ngoài, và cũng không làm phạm vi `text` co lại chỉ vì xuất hiện một cặp ngoặc mới.

### Một giới hạn tinh tế: block ngoài vẫn là ranh giới

```java
static String withinBlock(Object input) {
    {
        if (!(input instanceof String text)) {
            return "NO";
        }
        System.out.println(text); // Hợp lệ: sau guard clause trong cùng block.
    }

    // System.out.println(text); // Không hợp lệ: đã ra khỏi block chứa if.
    return "DONE";
}
```

Ngay cả khi nhánh không khớp đã `return`, phạm vi được giới thiệu bởi `if` vẫn gắn với **block bao quanh câu lệnh đó**. Trong ví dụ, phần sau block độc lập không được dùng `text`.

Điều này cho thấy **flow scoping không xóa bỏ quy tắc phạm vi của block**; hai quy tắc cùng áp dụng.

## 6. Guard clause trong block lồng nhau: biến còn dùng được sau `if`

Một trường hợp hữu ích là kiểm tra kiểu theo hướng phủ định:

```java
static String normalized(Object input) {
    if (!(input instanceof String text)) {
        return "NOT_TEXT";
    }

    // Chỉ đến được đây nếu input instanceof String text đã đúng.
    return text.strip();
}
```

Giải thích theo luồng điều khiển:

- Nếu `input` không phải `String` hoặc là `null`, `instanceof` là `false`, phép phủ định cho `true`, phương thức `return` ngay.
- Nếu chương trình chạy đến `text.strip()`, phép phủ định đã là `false`, nên pattern ban đầu chắc chắn khớp.

Với **block lồng nhau**, nguyên tắc vẫn vậy:

```java
static String nestedGuard(Object outer, Object inner) {
    if (!(outer instanceof String prefix)) {
        return "INVALID_PREFIX";
    }

    {
        if (!(inner instanceof String suffix)) {
            return "INVALID_SUFFIX";
        }
        return prefix + ":" + suffix;
    }
}
```

Trong block con:

- `prefix` đã khớp ở tầng ngoài, vẫn dùng được.
- `suffix` được chứng minh đã khớp vì nhánh không khớp đã `return`.
- `return prefix + ":" + suffix` dùng đồng thời cả hai biến.

### Vì sao chỉ in lỗi rồi đi tiếp là chưa đủ?

```java
// KHÔNG BIÊN DỊCH:
// if (!(input instanceof String text)) {
//     System.out.println("Not a String");
// }
// System.out.println(text.length());
```

Nhánh không khớp chỉ in thông báo rồi tiếp tục. Có một đường đi đến `text.length()` trong đó `text` chưa khớp. Nếu mục đích là loại giá trị sai kiểu, cần `return` hoặc `throw`, hoặc dùng một nhánh `else` mà ở đó pattern đã được đảm bảo.

### Phân biệt `return` và `break`

`return` thoát khỏi phương thức; `break` thông thường chỉ thoát khỏi vòng lặp hoặc `switch` gần nhất. Trong block lồng nhau có vòng lặp, **không thể thay máy móc `return` bằng `break` rồi cho rằng biến pattern còn hiệu lực ở mọi câu lệnh phía sau**. Phải xét chính xác đường đi thực thi sau `break`.

## 7. Pattern variable trong vòng lặp có block con

Vòng lặp thường tạo ra nhiều block lồng nhau: thân vòng lặp, nhánh `if` và block tính toán bên trong nhánh.

```java
static int sumLengths(Object[] values) {
    int total = 0;

    for (Object value : values) {
        if (value instanceof String text) {
            {
                String normalized = text.strip();
                total += normalized.length();
            }

            // text vẫn được dùng trong nhánh if này.
            // normalized không còn được dùng tại đây.
        }

        // Không thể dùng text ở đây: lần lặp này
        // có thể value không phải String.
    }

    return total;
}
```

Mỗi lần lặp, `value` là phần tử đang xét. Khi pattern khớp, `text` thuộc lần kiểm tra đó và có thể dùng trong các block con của nhánh. Không có biến `text` nào được bảo đảm sau nhánh `if`, cũng không có biến `text` để dùng ngoài vòng lặp.

Không nên mô tả biến pattern là “tồn tại xuyên suốt tất cả các lần lặp”. Cách đúng là: **mỗi lần thực thi điều kiện, nếu mẫu khớp, biến được ràng buộc với giá trị của lần kiểm tra đó ở phạm vi cho phép**.

## 8. Đặt tên và khai báo trùng trong block lồng nhau

Với biến cục bộ của Java, một block con thông thường **không được khai báo lại tên biến cục bộ đang ở trong phạm vi của block cha**. Quy tắc này cũng ảnh hưởng đến biến pattern.

Ví dụ không biên dịch:

```java
// KHÔNG HỢP LỆ:
// if (input instanceof String text) {
//     {
//         String text = "other"; // Trùng tên biến pattern đang trong phạm vi.
//         System.out.println(text);
//     }
// }
```

Thậm chí biến cục bộ đã có trước cũng có thể khiến khai báo biến pattern mới bị từ chối:

```java
// KHÔNG HỢP LỆ:
// String text = "existing";
// if (input instanceof String text) {  // Trùng tên local text.
//     System.out.println(text);
// }
```

Cách sửa là đặt tên khác nhau, hoặc chỉ dùng biến đã có nếu kiểu của nó đã đủ cụ thể.

Ở hai block **không giao nhau về phạm vi**, dùng lại tên có thể hợp lệ:

```java
if (first instanceof String text) {
    System.out.println(text);
}

if (second instanceof String text) {
    System.out.println(text);
}
```

Hai `text` ở trên là hai khai báo riêng biệt trong hai nhánh `if` độc lập. Chúng không tồn tại đồng thời trong một phạm vi chồng lấn.

### Pattern variable và lambda trong block con

Một lambda có thể đọc biến pattern từ phạm vi bao ngoài nếu biến đó là `final` hoặc **effectively final** (không bị gán lại sau khi nhận giá trị ban đầu):

```java
if (input instanceof String text) {
    Runnable action = () -> System.out.println(text.toUpperCase());
    action.run();
}
```

Đây là ví dụ minh họa hợp lệ trong một phương thức có `Object input`. Nếu gán lại `text` trong nhánh này, đoạn lambda có thể bị từ chối vì `text` không còn effectively final. Điều kiện để lambda bắt biến cục bộ là quy tắc riêng của Java, ngoài việc pattern đã khớp.

## 9. Chương trình Java 17 hoàn chỉnh: quan sát các mức phạm vi

Tạo file **`NestedPatternScopeDemo.java`**:

```java
import java.util.List;

public class NestedPatternScopeDemo {

    static String firstElement(Object input) {
        if (input instanceof List<?> items) {
            if (items.isEmpty()) {
                return "EMPTY_LIST";
            }

            Object first = items.get(0);
            if (first instanceof String text) {
                if (text.isBlank()) {
                    return "BLANK_STRING";
                }

                {
                    String clean = text.strip();
                    return "TEXT:" + clean;
                }
            }

            return "OTHER_ELEMENT";
        }
        return "NOT_LIST";
    }

    static String withEarlyReturn(Object input) {
        if (!(input instanceof String text)) {
            return "NOT_TEXT";
        }

        {
            String normalized = text.strip();
            if (normalized.isEmpty()) {
                return "BLANK";
            }
            return "OK:" + normalized;
        }
    }

    static String combine(Object left, Object right) {
        if (left instanceof String text) {
            if (right instanceof Integer count) {
                if (count > 0) {
                    return text.repeat(count);
                }
            }
            return "NO_REPEAT";
        }
        return "NOT_STRING";
    }

    static int totalLength(Object[] inputs) {
        int total = 0;
        for (Object input : inputs) {
            if (input instanceof String text) {
                {
                    String normalized = text.strip();
                    total += normalized.length();
                }
            }
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(firstElement(List.of("  Java  ")));
        System.out.println(firstElement(List.of("  ")));
        System.out.println(firstElement(List.of(42)));
        System.out.println(firstElement(List.of()));
        System.out.println(firstElement(null));

        System.out.println(withEarlyReturn("  scope  "));
        System.out.println(withEarlyReturn(12));
        System.out.println(withEarlyReturn("  "));

        System.out.println(combine("Go", 2));
        System.out.println(combine("Go", 0));
        System.out.println(combine(7, 2));

        System.out.println(totalLength(
                new Object[] {" a ", null, 12, "BB", " "}));
    }
}
```

Dùng JDK 17 hoặc mới hơn:

```bash
javac --release 17 NestedPatternScopeDemo.java
java NestedPatternScopeDemo
```

Kết quả in ra, theo đúng thứ tự:

```text
TEXT:Java
BLANK_STRING
OTHER_ELEMENT
EMPTY_LIST
NOT_LIST
OK:scope
NOT_TEXT
BLANK
GoGo
NO_REPEAT
NOT_STRING
3
```

**Vì sao chương trình hoạt động đúng?**

1. `firstElement` khớp `List<?> items`, kiểm tra danh sách rỗng trước khi lấy phần tử đầu. Nếu phần tử đầu là `String text`, cả block `if (text.isBlank())` và block độc lập chứa `clean` đều đọc được `text`. Dữ liệu `null` không khớp `List`, nên trả `NOT_LIST`.
2. `withEarlyReturn` chỉ đi qua nhánh đầu khi dữ liệu không phải `String`; sau đó `text` đã được bảo đảm trong block con. Chuỗi chỉ chứa khoảng trắng trở thành rỗng sau `strip()`.
3. `combine` dùng `text` từ nhánh ngoài và `count` từ nhánh trong. Chỉ khi số lần lặp lớn hơn 0 mới trả chuỗi lặp; mọi trường hợp khác được xử lý bằng nhánh tương ứng.
4. `totalLength` xét từng phần tử độc lập, chỉ cộng độ dài các giá trị `String` sau `strip()`: `" a "` dài 1, `"BB"` dài 2, `" "` dài 0; tổng là 3.

Các ví dụ cố tình đặt block độc lập ở vài nơi để người học quan sát sự khác biệt giữa biến pattern được giới thiệu từ điều kiện và biến cục bộ khai báo bên trong block.

## 10. Các lỗi thường gặp khi block lồng nhiều tầng

| Lỗi | Tại sao sai? | Cách sửa |
| --- | --- | --- |
| Dùng `text` trong `else` của `if (x instanceof String text)` | `else` nghĩa là pattern không khớp | Chỉ dùng `text` tại nhánh chắc chắn khớp |
| Dùng `text` sau `if` mà nhánh không khớp vẫn có thể đi tiếp | Không có bảo đảm gán giá trị cho `text` | Dùng `return`/`throw` ở nhánh loại trừ hoặc chuyển mã vào nhánh hợp lệ |
| Dùng biến cục bộ `clean` bên ngoài block khai báo | Biến cục bộ tuân theo phạm vi block | Đưa nơi sử dụng vào cùng block hoặc khai báo biến ở cấp thích hợp |
| Khai báo `String text` trong block con khi biến pattern `text` đang có hiệu lực | Khai báo tên trùng trong phạm vi chồng lấn | Chọn tên khác |
| Cho rằng mọi block con đều biết biến pattern của một nhánh anh em | Nhánh anh em có thể không khớp cùng pattern | Xét đúng đường đi và điều kiện cụ thể |
| Dùng `list.get(0)` mà không kiểm tra danh sách rỗng | Lỗi runtime, không phải lỗi phạm vi biến | Kiểm tra `isEmpty()` hoặc kích thước trước |
| Dùng `text` sau khi ra khỏi block bao quanh câu lệnh giới thiệu biến | Phạm vi cú pháp của block đã hết | Trả kết quả ra khỏi block hoặc thiết kế lại dữ liệu cần dùng |

Một lưu ý khác: `instanceof` trả `false` khi gặp `null`, nên không có pattern variable nào được ràng buộc cho giá trị `null`. Nếu bài toán cần xử lý `null`, phải thiết kế nhánh tương ứng.

## 11. Bài tập tự đánh giá

### Bài 1 — biến nào còn trong phạm vi?

Giả sử đã khai báo `Object value`:

```java
if (value instanceof String text) {
    int count = text.length();

    if (count > 2) {
        String message = text.toUpperCase();
        System.out.println(message);
    }

    System.out.println(text);
    System.out.println(count);
    // System.out.println(message); // (A)
}
// System.out.println(text);         // (B)
```

**Đáp án:** Hai dòng `System.out.println(text)` và `System.out.println(count)` trong nhánh ngoài hợp lệ. Bỏ chú thích dòng (A) sẽ gây lỗi vì `message` thuộc block `if` trong. Bỏ chú thích dòng (B) gây lỗi vì sau `if` ngoài, không có bảo đảm `value` đã khớp `String`.

### Bài 2 — phát hiện lỗi ở nhánh anh em

```java
// KHÔNG BIÊN DỊCH:
// if (value instanceof String text) {
//     System.out.println(text.length());
// } else {
//     if (value == null) {
//         System.out.println(text); // (A)
//     }
// }
```

**Đáp án:** Dòng (A) sai. Chạy vào `else` chứng tỏ điều kiện `instanceof` đầu tiên **không khớp**. Mở thêm một block `if (value == null)` bên trong `else` không thay đổi điều đó.

### Bài 3 — sửa điều kiện phủ định để dùng biến sau block con

Cho một phương thức:

```java
static String demo(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Not String");
    }
    return text.toUpperCase(); // Lỗi
}
```

**Cách sửa:** thay thông báo đơn lẻ bằng một đường thoát:

```java
static String demo(Object input) {
    if (!(input instanceof String text)) {
        return "Not String";
    }
    return text.toUpperCase();
}
```

Sau `if`, tất cả đường đi còn lại đều yêu cầu mẫu `String text` đã khớp.

### Bài 4 — tự triển khai

Viết một phương thức nhận `Object input`. Nếu là `List<?>` không rỗng và phần tử đầu là `String` có ít nhất 3 ký tự sau `strip()`, trả về chữ hoa của phần tử đó. Nếu không, trả về `"INVALID"`. Dùng ba tầng kiểm tra và chỉ dùng biến pattern trong các vùng đã khớp. Thử với `List.of("  java  ")`, `List.of("x")`, `List.of(5)`, `List.of()` và `null`.

Kết quả mong đợi lần lượt: `"JAVA"`, `"INVALID"`, `"INVALID"`, `"INVALID"`, `"INVALID"`.

## 12. Ghi nhớ và áp dụng

Với **pattern variable trong block lồng nhau**, có thể dùng một quy trình ngắn khi đọc mã:

1. Xác định biểu thức nào giới thiệu biến, chẳng hạn `if (input instanceof String text)`.
2. Tìm các nhánh mà biểu thức chắc chắn đúng; các block con của nhánh này có thể dùng `text`.
3. Tìm những chỗ rời khỏi nhánh đó, nhất là `else`, sau `if`, và sau khi ra khỏi block chứa câu lệnh.
4. Nếu biến vẫn được dùng sau `if`, kiểm tra đường đi không khớp có thực sự **không thể tiếp tục** nhờ `return` hoặc `throw` hay không.
5. Kiểm tra thêm phạm vi của các biến cục bộ khai báo trong block nhỏ hơn và nguy cơ trùng tên.

**Thông điệp chính:** dấu `{ }` quyết định phạm vi cú pháp của nhiều biến cục bộ; còn pattern variable cần thêm bảo đảm **so khớp thành công theo luồng điều khiển**. Block con có thể dùng pattern variable từ block cha khi bảo đảm đó còn đúng. Chỉ dựa vào mức thụt đầu dòng sẽ không đủ để đánh giá phạm vi biến.

## Tài liệu tham khảo chính thức

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [Java SE 17 Language Specification, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [Java SE 17 Language Specification, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30)
