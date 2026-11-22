# Throw trong nhánh switch và luồng điều khiển có trả về giá trị trong Java

Trong Java, `throw` **chấm dứt bất thường đường thực thi hiện tại** bằng cách ném một đối tượng ngoại lệ. Điều này đặc biệt quan trọng khi một nhánh `switch` phải quyết định **trả về giá trị hay báo lỗi**: nhánh hợp lệ cung cấp một kết quả, còn nhánh không hợp lệ có thể dùng `throw` để ngăn chương trình tiếp tục với giá trị giả.

Từ Java 14, `switch expression` là tính năng chuẩn; Java 17+ sử dụng được cú pháp mũi tên `->`, `yield` và `throw` trong nhánh `switch` mà không cần bật preview. Cần phân biệt rõ:

- **`switch expression`:** Toàn bộ `switch` tham gia vào một biểu thức, có giá trị để gán hoặc trả về. Mỗi nhánh được chọn phải cung cấp giá trị theo quy tắc ngôn ngữ, hoặc hoàn tất bất thường, chẳng hạn bằng `throw`.
- **`switch statement`:** Toàn bộ `switch` là một câu lệnh điều khiển. Nhánh có thể thực hiện thao tác, thoát bằng `break`, hoặc trong ngữ cảnh phù hợp dùng `return`, `throw`.
- **`throw`:** Là câu lệnh ném ngoại lệ, **không phải một biểu thức tạo ra giá trị**. Trong một `switch expression`, một nhánh `throw` hợp lệ vì nhánh đó không kết thúc bình thường; Java không yêu cầu nhánh ném phải cung cấp giá trị.

Hiểu ba điểm trên giúp tránh sai lầm thường gặp khi kết hợp `return switch (...)`, `yield` và xử lý ngoại lệ.

## 1. Tình huống cơ bản: giá trị hợp lệ thì trả về, không hợp lệ thì throw

Ví dụ phương thức ánh xạ một mã thao tác thành giới hạn:

~~~java
static int quota(String mode) {
    return switch (mode) {
        case "fast" -> 12;
        case "safe" -> 6;
        default -> throw new IllegalArgumentException(
                "Chế độ không hỗ trợ: " + mode);
    };
}
~~~

Đây là **đoạn phương thức minh họa**, có thể đặt trong một lớp Java. Diễn giải:

1. `switch (mode)` được đánh giá và chọn một nhánh.
2. Với `"fast"`, biểu thức `switch` có giá trị `12`; `return` của phương thức trả về `12`.
3. Với `"safe"`, biểu thức `switch` có giá trị `6`.
4. Với chuỗi khác, câu lệnh `throw new IllegalArgumentException(...)` chạy. Cả biểu thức `switch` lẫn phương thức không trả về `int` trên đường đi đó; ngoại lệ được truyền ra cho bên gọi nếu chưa được bắt.

Điểm cốt lõi: phương thức khai báo `int` **không bắt buộc trả về một số ở đường dẫn ném ngoại lệ**. Mọi đường thực thi kết thúc bình thường phải trả đúng kiểu; đường đi `throw` kết thúc bất thường nên không cần `return 0` để “đủ kiểu”.

### Vì sao không trả một giá trị mặc định tùy tiện?

~~~java
static int quotaWrong(String mode) {
    return switch (mode) {
        case "fast" -> 12;
        case "safe" -> 6;
        default -> 0;
    };
}
~~~

Đoạn này **biên dịch được**, nhưng nếu `0` không phải quy ước hợp lệ của API, bên gọi có thể tưởng thao tác thành công và tiếp tục với dữ liệu sai. Khi đầu vào vi phạm hợp đồng, ném ngoại lệ thường rõ nghĩa hơn trả một “giá trị phép” chưa được định nghĩa.

Ngược lại, nếu nghiệp vụ quy định mọi chế độ không nhận diện đều phải có hạn mức `0` thì `default -> 0` lại là lựa chọn đúng. `throw` không phải mục tiêu tự thân: hãy chọn kết quả theo **hợp đồng của phương thức**.

## 2. Quy tắc quan trọng của `switch expression`

Xét một biểu thức gán kết quả:

~~~java
int level = switch (name) {
    case "basic" -> 1;
    case "pro" -> 2;
    default -> throw new IllegalArgumentException("Tên không hợp lệ");
};
~~~

Đây là **đoạn minh họa** cần biến `name` phù hợp trong một phương thức. Nhánh chọn `"basic"` hoặc `"pro"` hoàn tất bình thường với giá trị `int`. Nhánh `default` ném ngoại lệ và không cung cấp giá trị.

Không nên giải thích `throw` như một giá trị `int` đặc biệt. Nó là **kết thúc bất thường** của nhánh đang được thực thi; vì thế nó không gây xung đột với yêu cầu loại `int` của các nhánh trả giá trị.

### Dạng một biểu thức sau mũi tên

~~~java
case "basic" -> 1;
~~~

Phía phải của mũi tên là biểu thức `1`, cung cấp giá trị cho `switch expression`.

### Dạng một khối có nhiều lệnh và `yield`

~~~java
case "pro" -> {
    int base = 2;
    int multiplier = 3;
    yield base * multiplier;
}
~~~

Khi một nhánh của `switch expression` dùng khối `{ ... }`, `yield` cung cấp giá trị của biểu thức `switch`. Ở ví dụ này, kết quả là `6`.

### Dạng ném ngoại lệ

~~~java
default -> throw new IllegalArgumentException("Không có cấu hình");
~~~

Phía phải là **`throw` statement**; nhánh này không hoàn thành bình thường và không có giá trị `yield`.

### Dạng khối có kiểm tra rồi ném hoặc yield

~~~java
case "custom" -> {
    if (limit < 0) {
        throw new IllegalArgumentException("limit không được âm");
    }
    yield limit * 2;
}
~~~

Đây là nhánh minh họa có biến `limit` trong phạm vi. Khi `limit < 0`, nhánh ném ngoại lệ; khi hợp lệ, nhánh cung cấp giá trị bằng `yield`. Vì đường `throw` không cần sinh giá trị, đây là cách viết hợp lệ.

Trong khối nhánh của `switch expression`, **mọi đường có thể kết thúc bình thường mà thiếu `yield` là sai**. Một khối có `throw` trên một nhánh điều kiện vẫn cần `yield` hoặc ném ngoại lệ trên các đường còn lại.

## 3. Phân biệt `yield`, `return` và `throw`

Ba lệnh đều ảnh hưởng luồng điều khiển nhưng mục đích khác nhau.

| Lệnh | Điều xảy ra | Thường dùng ở đâu? |
| --- | --- | --- |
| `yield value;` | Hoàn tất nhánh của `switch expression`, cung cấp giá trị cho chính biểu thức `switch` | Khối nhánh `switch expression` |
| `return value;` | Kết thúc phương thức đang chạy bình thường và trả giá trị cho bên gọi | Thân phương thức, hoặc khối của `switch statement` khi thích hợp |
| `throw exception;` | Kết thúc bất thường bằng cách ném đối tượng ngoại lệ | Trong phương thức, trong nhánh `switch expression` hoặc `switch statement` |

Ví dụ hợp lệ với `yield`:

~~~java
static int calculate(String key) {
    int result = switch (key) {
        case "double" -> {
            int source = 7;
            yield source * 2;
        }
        case "one" -> 1;
        default -> throw new IllegalArgumentException("Key sai: " + key);
    };
    return result;
}
~~~

Phương thức trên là **đoạn hoàn chỉnh về logic** nhưng cần được đặt trong một lớp Java. `yield 14;` chỉ chuyển giá trị `14` ra khỏi `switch expression` để gán cho `result`; lệnh `return result;` mới trả giá trị từ phương thức `calculate`.

### Không dùng `return` bên trong khối của `switch expression`

Ví dụ **sai, không biên dịch**:

~~~java
static int invalid(String key) {
    return switch (key) {
        case "one" -> {
            return 1;  // Không được return từ bên trong switch expression.
        }
        default -> 0;
    };
}
~~~

Ở `switch expression`, khối nhánh phải dùng `yield` để đưa ra giá trị hoặc `throw` để kết thúc bất thường. Sửa thành:

~~~java
static int valid(String key) {
    return switch (key) {
        case "one" -> {
            yield 1;
        }
        default -> 0;
    };
}
~~~

### Không coi `throw` là một toán hạng thông thường

Cú pháp sau **sai** trong Java:

~~~java
int value = flag ? 10 : throw new IllegalArgumentException("Sai");
~~~

`throw` là câu lệnh, không phải biểu thức dùng được ở vị trí toán hạng thứ ba của `?:`. Có thể viết:

~~~java
int value = switch (flag) {
    case true -> 10;
    case false -> throw new IllegalArgumentException("Sai");
};
~~~

**Tuy nhiên, đoạn `switch (flag)` trên cũng không hợp lệ trong Java 17:** selector của `switch` không thể là kiểu nguyên thủy `boolean` (Java 17 chưa hỗ trợ `switch` trên `boolean` như ví dụ đó). Để đúng Java 17, hãy dùng selector `int` hoặc `String`:

~~~java
int value = switch (flag ? 1 : 0) {
    case 1 -> 10;
    default -> throw new IllegalArgumentException("Sai");
};
~~~

Các đoạn này là **minh họa cú pháp**, biến `flag` là một `boolean` có sẵn. Việc trình bày cả hai cách không hợp lệ làm rõ hai giới hạn độc lập: `throw` không phải biểu thức dùng trong `?:`, và `boolean` không phải selector `switch` tiêu chuẩn trong Java 17.

## 4. `switch statement`: nhánh throw khác nhánh return

`switch statement` là một **câu lệnh**, không trả ra một giá trị cho toán tử gán. Tuy nhiên phương thức bao quanh vẫn có thể trả giá trị từ bên trong các khối nhánh:

~~~java
static int quotaStatement(String mode) {
    switch (mode) {
        case "fast" -> {
            return 12;
        }
        case "safe" -> {
            return 6;
        }
        default -> throw new IllegalArgumentException(
                "Chế độ không hỗ trợ: " + mode);
    }
}
~~~

Đây là phương thức minh họa hợp lệ trong Java 17+. Khi `mode` hợp lệ, khối nhánh gọi `return` để **trả khỏi phương thức**; khi không hợp lệ, `throw` làm phương thức kết thúc bất thường.

Điểm khác biệt so với `return switch (...)`:

- Với **`switch expression`**, các nhánh sinh giá trị `-> 12`, `-> 6`; phương thức có một `return switch (...)` bao quanh.
- Với **`switch statement`**, các nhánh dùng `return` trong khối để trả khỏi phương thức.
- Cả hai có thể dùng nhánh `default -> throw ...` để không trả giá trị giả.

### Vì sao phải có dấu ngoặc quanh `return` ở nhánh mũi tên của switch statement?

Một `switch rule` sau `->` có phần thân thuộc một trong các loại mà cú pháp cho phép, như biểu thức dạng câu lệnh, khối hoặc `throw` statement. Đoạn sau không phải cách viết hợp lệ:

~~~java
switch (mode) {
    case "fast" -> return 12;  // Sai: return không phải phần thân trực tiếp ở đây.
    default -> throw new IllegalArgumentException();
}
~~~

Sửa bằng khối:

~~~java
switch (mode) {
    case "fast" -> {
        return 12;
    }
    default -> throw new IllegalArgumentException();
}
~~~

Hai đoạn trên cần nằm trong một phương thức trả `int` và có biến `mode` phù hợp. Với `switch expression`, `case "fast" -> 12;` lại là cách đúng để trả **giá trị biểu thức**.

### Dạng switch statement cổ điển dùng dấu hai chấm

Java 17 vẫn hỗ trợ cú pháp `case ...:` và lệnh `break`:

~~~java
static int quotaClassic(String mode) {
    switch (mode) {
        case "fast":
            return 12;
        case "safe":
            return 6;
        default:
            throw new IllegalArgumentException(
                    "Chế độ không hỗ trợ: " + mode);
    }
}
~~~

Phương thức này hợp lệ. `return` kết thúc cả phương thức và `throw` kết thúc bất thường, nên không cần `break` ở các nhánh đó. Nhưng nếu một nhánh cổ điển chỉ chạy vài câu lệnh bình thường mà không `break`, `return` hoặc `throw`, chương trình có thể **rơi tiếp (fall-through)** sang nhánh kế tiếp; cú pháp mũi tên `->` giúp tránh kiểu rơi tiếp không chủ ý đó.

## 5. Tính bao phủ (exhaustiveness) và nhánh ném ngoại lệ

**`switch expression` phải bao phủ mọi giá trị selector có thể xảy ra theo quy tắc biên dịch.** Cách phổ biến với `String` hoặc `int` là khai báo `default`. `default` có thể cung cấp giá trị hoặc ném ngoại lệ.

~~~java
static String stateLabel(int state) {
    return switch (state) {
        case 0 -> "READY";
        case 1 -> "RUNNING";
        default -> throw new IllegalArgumentException(
                "Mã trạng thái không biết: " + state);
    };
}
~~~

Ở đây, các giá trị `0` và `1` cho ra chuỗi; mọi giá trị khác ném ngoại lệ. Nhánh `throw` **được tính là một nhánh bao phủ hợp lệ** dù không tạo ra `String`.

Nếu bỏ `default` trong `switch expression` cho `int` mà không còn cách bao phủ toàn bộ các giá trị, trình biên dịch sẽ báo lỗi vì biểu thức `switch` không exhaustive. Đặt `default -> throw ...` là cách biểu đạt rõ ràng rằng giá trị ngoài miền hợp lệ **không được chấp nhận**.

### Trường hợp enum: bao phủ đầy đủ bằng các hằng số

~~~java
enum Stage { NEW, ACTIVE, CLOSED }

static int priority(Stage stage) {
    return switch (stage) {
        case NEW -> 1;
        case ACTIVE -> 2;
        case CLOSED -> throw new IllegalStateException(
                "Giai đoạn đóng không có độ ưu tiên");
    };
}
~~~

Hai khai báo trên có thể đặt trong một lớp Java. Với `enum Stage` đang có đúng ba hằng số, ba nhánh đã bao phủ toàn bộ các hằng số, vì vậy không bắt buộc `default`. Nhánh `CLOSED` dùng `throw` vẫn đủ để tạo một `switch expression` hợp lệ.

Khi thêm hằng số mới vào `enum` rồi biên dịch lại mã sử dụng, `switch expression` không có `default` thường phải được cập nhật để vẫn exhaustiveness. Đây có thể là chủ đích tốt: trình biên dịch nhắc người phát triển xét từng trạng thái mới.

Đừng coi `default -> throw` luôn cần thiết trong mọi `switch expression`. Với enum có đầy đủ case, bỏ `default` thường giúp phát hiện sự thay đổi miền giá trị khi build; chọn cách nào phải dựa trên hợp đồng API.

### Một nhánh ném không làm toàn bộ switch vô giá trị

~~~java
int x = switch (code) {
    case 1 -> 10;
    case 2 -> 20;
    default -> throw new IllegalArgumentException("code sai");
};
~~~

Những nhánh hoàn tất bình thường đều là giá trị `int`; nhánh `throw` không cần “đóng góp một kiểu” cho việc tạo kết quả. Tuy vậy nếu các nhánh còn lại trả kiểu không tương thích với ngữ cảnh đích, trình biên dịch vẫn báo lỗi loại dữ liệu.

## 6. Checked exception trong nhánh `switch`

`throw` trong `switch` chịu **chính quy tắc checked/unchecked** như ở mọi nơi khác. `throw new IOException(...)` là ném checked exception; phương thức bao quanh phải bắt hoặc khai báo. `throw new IllegalArgumentException(...)` là unchecked, không bắt buộc khai báo `throws`.

Ví dụ checked:

~~~java
static int loadQuota(String mode) throws java.io.IOException {
    return switch (mode) {
        case "standard" -> 5;
        case "offline" -> throw new java.io.IOException(
                "Không thể tải hạn mức khi ngoại tuyến");
        default -> throw new IllegalArgumentException(
                "Chế độ không hợp lệ: " + mode);
    };
}
~~~

Phương thức này biên dịch hợp lệ trong Java 17+ vì đã khai báo `throws IOException`. Khi `mode` là `"offline"`, không có `int` nào được trả về. Bên gọi phải tuân thủ hợp đồng checked của `IOException`.

### Không khai báo checked exception: lỗi biên dịch

Ví dụ **sai**:

~~~java
static int invalidChecked(String mode) {
    return switch (mode) {
        case "offline" -> throw new java.io.IOException("Mất kết nối");
        default -> 5;
    };
}
~~~

Trình biên dịch yêu cầu bắt hoặc khai báo `IOException`. Sửa bằng `throws java.io.IOException` trong chữ ký hoặc xử lý qua `try/catch` phù hợp tại tầng có khả năng quyết định.

Việc nhánh `offline` chỉ chạy khi selector khớp không tự miễn yêu cầu checked tại thời điểm biên dịch. Ngược lại, checked exception **không bắt buộc phương thức trả một số đặc biệt trong nhánh ném**.

## 7. Ví dụ Java 17+ hoàn chỉnh: trả kết quả, yield và throw

Chương trình sau kiểm tra trực tiếp ba cách sử dụng:

1. `switch expression` trả `int` bằng nhánh biểu thức hoặc `yield`.
2. `switch expression` ném checked hoặc unchecked exception theo nhánh.
3. `switch statement` dùng `return` trong khối nhánh và `throw` ở `default`.

Lưu toàn bộ chương trình trong tệp **`SwitchThrowDemo.java`**:

~~~java
public class SwitchThrowDemo {
    static class QuotaUnavailableException extends Exception {
        QuotaUnavailableException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        for (String mode :
                new String[] {"fast", "safe", "blocked", "unknown"}) {
            try {
                System.out.println(mode + " => " + quota(mode));
            } catch (QuotaUnavailableException e) {
                System.out.println(
                        mode + " => checked: " + e.getMessage());
            } catch (IllegalArgumentException e) {
                System.out.println(
                        mode + " => unchecked: " + e.getMessage());
            }
        }

        System.out.println(
                "statement safe => " + quotaStatement("safe"));

        try {
            quotaStatement("wrong");
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "statement wrong => " + e.getMessage());
        }
    }

    static int quota(String mode)
            throws QuotaUnavailableException {
        return switch (mode) {
            case "fast" -> 12;
            case "safe" -> {
                int base = 4;
                yield base + 2;
            }
            case "blocked" -> throw new QuotaUnavailableException(
                    "Hạn mức tạm khóa");
            default -> throw new IllegalArgumentException(
                    "Chế độ lạ: " + mode);
        };
    }

    static int quotaStatement(String mode) {
        switch (mode) {
            case "fast" -> {
                return 12;
            }
            case "safe" -> {
                return 6;
            }
            default -> throw new IllegalArgumentException(
                    "Không hỗ trợ: " + mode);
        }
    }
}
~~~

Biên dịch và chạy (JDK 17 trở lên):

~~~bash
javac SwitchThrowDemo.java
java SwitchThrowDemo
~~~

**Stdout chính xác:**

~~~text
fast => 12
safe => 6
blocked => checked: Hạn mức tạm khóa
unknown => unchecked: Chế độ lạ: unknown
statement safe => 6
statement wrong => Không hỗ trợ: wrong
~~~

### Lần theo từng nhánh

- **`fast`:** Nhánh `case "fast" -> 12;` hoàn tất `switch expression` với `12`; `return` của phương thức `quota` chuyển giá trị đó về `main`.
- **`safe`:** Nhánh khối khai báo `base = 4` rồi `yield base + 2;`, cung cấp giá trị `6` cho biểu thức `switch`; phương thức trả `6`.
- **`blocked`:** Nhánh `case "blocked" -> throw new QuotaUnavailableException(...)` tạo và ném checked exception. Vì `quota` khai báo `throws QuotaUnavailableException`, `main` xử lý bằng `catch (QuotaUnavailableException e)`. Không có giá trị `int` được trả về trên đường đi này.
- **`unknown`:** Nhánh `default` ném `IllegalArgumentException`, được khối `catch` unchecked tương ứng bắt.
- **`quotaStatement("safe")`:** `switch statement` không tự là một biểu thức trả giá trị; `return 6;` trong khối nhánh thoát khỏi phương thức.
- **`quotaStatement("wrong")`:** `default -> throw ...` khiến phương thức kết thúc bất thường, không in một dòng kết quả thành công; thông báo ở `main` được tạo bởi `catch`.

Trong chương trình, hai khối `catch` nằm cạnh nhau không tranh nhau nhận cùng một loại: `QuotaUnavailableException` là checked kế thừa `Exception`; `IllegalArgumentException` là unchecked kế thừa `RuntimeException`. Đầu ra không có dòng stack trace vì mọi ngoại lệ do ví dụ phát sinh đều được bắt ở `main`.

## 8. Luồng điều khiển và tính “mọi đường đều trả về giá trị”

Phương thức có kiểu trả về khác `void` phải thỏa các quy tắc của Java về khả năng hoàn tất bình thường và trả về giá trị. Có thể mô hình hóa một phương thức như sau:

~~~text
return switch (mode)
    |
    +-- nhánh hợp lệ --> sinh giá trị --> return cho caller
    |
    +-- nhánh bị cấm --> throw ngoại lệ --> tìm catch phù hợp
                                              |
                                              +-- caller bắt và xử lý
                                              +-- hoặc ngoại lệ tiếp tục lan truyền
~~~

Điểm quan trọng là đường `throw` không đến câu lệnh `return` nhưng vẫn hợp lệ: phương thức không hoàn tất bình thường trên đường đó.

### Các trường hợp cần phân biệt

| Trường hợp | Hành vi |
| --- | --- |
| Nhánh `-> 10` của `switch expression` | Cung cấp giá trị `10` cho toàn biểu thức |
| Nhánh `-> { yield 10; }` | Cung cấp giá trị `10` cho toàn biểu thức |
| Nhánh `-> throw new RuntimeException()` | Không tạo giá trị, kết thúc bất thường |
| Nhánh `-> { throw new RuntimeException(); }` | Không tạo giá trị, kết thúc bất thường |
| Khối `switch statement` chứa `return 10;` | Trả về `10` từ phương thức |
| Khối `switch statement` chứa `throw ...;` | Kết thúc bất thường và tìm handler |
| Khối `switch statement` chỉ in log rồi kết thúc | Tiếp tục sau `switch statement` nếu có câu lệnh tiếp theo |

Ví dụ cuối cùng rất dễ gây nhầm:

~~~java
static int value(String mode) {
    switch (mode) {
        case "fast" -> System.out.println("fast");
        default -> System.out.println("other");
    }
    return 1;
}
~~~

Đây là một phương thức **hợp lệ**: `switch` chỉ in thông báo, sau đó `return 1;` mới trả về kết quả cho tất cả đầu vào. Đừng diễn giải `System.out.println(...)` trong `switch statement` như một nhánh tạo giá trị giống `switch expression`.

### Vì sao code này sai?

~~~java
static int broken(String mode) {
    switch (mode) {
        case "fast" -> {
            return 12;
        }
        case "safe" -> {
            System.out.println("safe");
        }
        default -> throw new IllegalArgumentException("mode sai");
    }
}
~~~

Đoạn minh họa này **không biên dịch**: nếu `mode` là `"safe"`, phương thức có thể hoàn tất bình thường mà không trả `int`. Đường `default -> throw` chỉ xử lý đầu vào khác; nó không cung cấp `return` cho đường `safe`. Muốn sửa, hãy trả kết quả ở nhánh `safe` hoặc đặt một `return` chung sau `switch statement` với hợp đồng thích hợp.

Đối với `switch expression`, một nhánh khối kết thúc bình thường mà không `yield` sẽ bị từ chối theo quy tắc riêng của biểu thức `switch`.

## 9. Tổ chức xử lý ngoại lệ khi dùng `return switch`

Tùy ý nghĩa của API, bạn có thể để ngoại lệ lan lên caller hoặc bắt ở ranh giới phù hợp:

~~~java
static int quotaOrDefault(String mode, int fallback) {
    try {
        return switch (mode) {
            case "fast" -> 12;
            case "safe" -> 6;
            default -> throw new IllegalArgumentException(
                    "Chế độ không hợp lệ");
        };
    } catch (IllegalArgumentException e) {
        return fallback;
    }
}
~~~

Phương thức minh họa trên **trả fallback** cho đầu vào không được hỗ trợ. Điều này chỉ hợp lý nếu hợp đồng thực sự cho phép dùng fallback. Nếu dùng sai chế độ là lỗi bắt buộc báo cho caller, nên để ngoại lệ lan truyền.

Đừng viết `catch (Exception e)` bao quanh mọi `switch` rồi trả giá trị cố định một cách im lặng: cách đó có thể che cả lỗi logic hoặc trạng thái mà ứng dụng phải điều tra.

### Vai trò của `finally` khi một nhánh throw hoặc return

~~~java
static int example(boolean fail) {
    try {
        return switch (fail ? "fail" : "ok") {
            case "ok" -> 9;
            default -> throw new IllegalStateException("không thành công");
        };
    } finally {
        System.out.println("cleanup");
    }
}
~~~

Đây là phương thức minh họa hợp lệ. Trong điều kiện chạy bình thường:

- `example(false)` in `cleanup` rồi trả `9`.
- `example(true)` in `cleanup`, sau đó ngoại lệ `IllegalStateException` tiếp tục lan ra ngoài.

`finally` thường chạy khi rời `try`, cả khi nhánh đã tạo giá trị `return` và khi nhánh ném ngoại lệ. Không nên đặt `return` hoặc ném ngoại lệ khác vô ý trong `finally` vì có thể che kết quả hoặc lỗi đang truyền. Các tình huống chấm dứt JVM bất thường có thể ngăn `finally` chạy.

## 10. `switch`, null và kiểu selector trong Java 17

Cú pháp nhánh `throw` không thay đổi các giới hạn kiểu của `switch` trong Java 17.

### Selector `null`

Nếu selector tham chiếu như `String mode` là `null`, `switch (mode)` trong Java 17 theo tính năng tiêu chuẩn sẽ ném `NullPointerException` trước khi chọn nhánh; `default` **không** phải nhánh tự động xử lý `null`.

~~~java
static int level(String name) {
    return switch (name) {
        case "low" -> 1;
        default -> throw new IllegalArgumentException("Tên không hợp lệ");
    };
}
~~~

Với `level(null)`, Java 17 thường ném `NullPointerException` tại đánh giá selector. Muốn lỗi theo hợp đồng của riêng mình, có thể kiểm tra trước:

~~~java
static int levelChecked(String name) {
    if (name == null) {
        throw new IllegalArgumentException("name không được null");
    }
    return switch (name) {
        case "low" -> 1;
        default -> throw new IllegalArgumentException("Tên không hợp lệ");
    };
}
~~~

Hai phương thức chỉ minh họa xử lý đầu vào. Không dùng `case null` hoặc pattern matching for switch như thể đó là cú pháp Java 17 chuẩn không cần preview; các tính năng pattern switch thay đổi theo phiên bản Java.

### Kiểu `boolean` trong switch Java 17

Java 17 tiêu chuẩn hỗ trợ `switch` trên một số kiểu nguyên thủy nguyên, các kiểu wrapper liên quan, `String` và `enum`; **không hỗ trợ selector `boolean`** theo cú pháp chuẩn Java 17. Vì thế:

~~~java
int x = switch (flag) {
    case true -> 1;
    default -> throw new IllegalArgumentException();
};
~~~

là **phản ví dụ không biên dịch với Java 17**, ngay cả khi ý định dùng `throw` hoàn toàn rõ. Nếu chỉ có điều kiện boolean, hãy dùng `if/else`:

~~~java
static int requireEnabled(boolean enabled) {
    if (!enabled) {
        throw new IllegalStateException("Chưa bật");
    }
    return 1;
}
~~~

Đây là phương thức hoàn chỉnh về logic, có thể đặt trong một lớp Java. Không cần ép mọi điều kiện đơn giản thành `switch`.

## 11. Các lỗi thường gặp

**Lỗi 1: Nghĩ rằng `throw` tạo ra một giá trị mặc định cho `switch expression`.**  
Sai. `throw` không cung cấp giá trị; nó kết thúc bất thường. Khi được bắt ở caller, caller xử lý ngoại lệ theo hợp đồng, chứ không nhận một `int` hay `String` giả.

**Lỗi 2: Dùng `return` trong khối của `switch expression`.**  
Khối nhánh phải `yield value`, `throw`, hoặc hoàn tất bất thường theo cách hợp lệ. `return` ở bên trong `switch expression` là lỗi biên dịch; `return switch (...)` ở bên ngoài biểu thức mới trả về từ phương thức.

**Lỗi 3: Thiếu `yield` trên một đường có thể kết thúc bình thường.**  
Nếu nhánh khối có điều kiện ném, nhánh còn lại phải cung cấp giá trị; không thể chỉ in log rồi kết thúc khối khi toàn bộ `switch` cần một giá trị.

**Lỗi 4: Viết `case X -> return value;` trong `switch statement`.**  
Cú pháp đúng với `return` là `case X -> { return value; }`. Nếu là `switch expression`, chỉ cần `case X -> value;` hoặc khối `yield`.

**Lỗi 5: Quên tính exhaustive của `switch expression`.**  
Đối với selector như `int` hoặc `String`, dùng `default` nếu cần bao phủ các giá trị không liệt kê. `default -> throw ...` là một cách xử lý hợp lệ khi đầu vào ngoài miền nên bị từ chối.

**Lỗi 6: Ném checked exception mà không bắt hoặc khai báo.**  
`case "offline" -> throw new IOException(...)` vẫn tuân thủ luật checked exception như mọi câu lệnh `throw` khác.

**Lỗi 7: Cho rằng `default` luôn xử lý `null`.**  
Với selector `String` là `null` trong Java 17 không dùng tính năng preview, một `NullPointerException` thường xuất hiện trước khi nhánh `default` chạy. Kiểm tra `null` trước nếu API muốn lỗi rõ hơn.

**Lỗi 8: Trả giá trị giả chỉ để ép mọi đường có giá trị.**  
Nếu đầu vào không hợp lệ, `default -> throw new IllegalArgumentException(...)` thường phản ánh hợp đồng tốt hơn `default -> 0` không có ngữ nghĩa.

**Lỗi 9: Giả định switch statement luôn phải trả về một giá trị.**  
`switch statement` có thể chỉ chạy các thao tác rồi tiếp tục sau cấu trúc. Nhưng nếu chính phương thức khai báo trả giá trị, nó vẫn phải thỏa quy tắc `return` trên mọi đường hoàn tất bình thường.

**Lỗi 10: Cố gắng đặt `throw` như một toán hạng biểu thức bất kỳ.**  
`throw` là statement. Cú pháp `case ... -> throw ...` được ngôn ngữ hỗ trợ riêng, không có nghĩa `throw` được phép xuất hiện thay mọi biểu thức trong `?:` hay ở toán hạng của phép cộng.

## 12. Bài tập tự kiểm tra

1. Vì sao phương thức `int quota(String mode)` vẫn biên dịch khi nhánh `default` chỉ `throw new IllegalArgumentException(...)` mà không trả `int`?
2. Trong `return switch (...)`, khi nào viết `case X -> 10;`, khi nào viết `case X -> { yield 10; }`?
3. Điều gì sai với `case X -> { return 10; }` khi nó nằm trong một `switch expression`? Cách viết đúng là gì?
4. Với `switch statement`, vì sao `case X -> { return 10; }` có thể hợp lệ trong phương thức trả `int`?
5. Nếu một nhánh `switch expression` ném `IOException`, phương thức bao quanh phải đáp ứng yêu cầu gì?
6. Vì sao `default -> throw ...` có thể làm biểu thức `switch` trên `int` đáp ứng exhaustiveness?
7. Trong Java 17, gọi phương thức sử dụng `switch (someString)` với selector `null` có chắc vào `default` không?
8. Khi `return switch (...)` nằm trong `try/finally`, `finally` có thường chạy trước khi phương thức thật sự trả giá trị hoặc ném lỗi ra ngoài không?
9. Có thể dùng `throw new RuntimeException(...)` làm nhánh thứ ba của toán tử `?:` như một biểu thức Java thông thường không?
10. Vì sao phiên bản `switch statement` chỉ ghi log ở một nhánh rồi đi tiếp có thể gây lỗi “missing return statement” cho một phương thức trả `int`?
11. Với `enum` đã được liệt kê đầy đủ trong `switch expression`, có bắt buộc có `default` không? Điểm hữu ích của việc bỏ `default` khi phát triển enum là gì?
12. Nếu `catch` quanh `return switch` bắt `IllegalArgumentException` rồi trả `fallback`, điều gì cần được xác định trong hợp đồng API trước khi chọn cách này?

### Gợi ý đáp án

1. Đường ném ngoại lệ không hoàn tất bình thường, nên không cần sinh `int`.
2. Dạng mũi tên ngắn khi chỉ có một biểu thức; khối `yield` khi cần thực hiện thêm lệnh.
3. `return` bị cấm trong khối của `switch expression`; đổi thành `yield 10;`.
4. Đây là `switch statement`; `return` trong khối hợp lệ và kết thúc phương thức.
5. Bắt hoặc khai báo checked `IOException`.
6. Vì xử lý tất cả selector còn lại bằng kết thúc bất thường cũng hợp lệ.
7. Không; selector `null` thường gây `NullPointerException` trong Java 17 tiêu chuẩn.
8. Có, khi luồng thoát phạm vi `try` bình thường; tránh viết code `finally` làm che lỗi hoặc kết quả.
9. Không, `throw` là câu lệnh chứ không phải toán hạng biểu thức thông thường.
10. Vì đường đó hoàn tất bình thường mà không trả giá trị cho phương thức.
11. Không nếu đã bao phủ enum; bỏ `default` có thể giúp compiler phát hiện case cần bổ sung khi enum thay đổi và biên dịch lại.
12. Xác định liệu đầu vào không hợp lệ được phép chuyển sang giá trị dự phòng hay phải báo lỗi cho caller.

## 13. Ghi nhớ

Trong một **`switch expression`**, các nhánh hợp lệ tạo giá trị bằng biểu thức hoặc `yield`; nhánh từ chối có thể dùng **`throw`** và không phải tạo ra giá trị. Trong một **`switch statement`**, khối nhánh có thể trực tiếp **`return`** khỏi phương thức hoặc **`throw`** để báo lỗi. Cả hai kiểu đều tuân thủ checked exception, quy tắc xử lý ngoại lệ và luồng điều khiển của Java. Khi thiết kế mã, hãy đặt câu hỏi: *nhánh này cần cung cấp kết quả hợp lệ hay phải chấm dứt bất thường vì đầu vào/trạng thái không hợp lệ?*