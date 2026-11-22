# Mô hình cờ bit và điều phối lệnh chuỗi trong Java

## 1. Bài toán thực hành tổng hợp

Một công cụ dòng lệnh cần quản lý nhiều trạng thái bật/tắt và xử lý lệnh người dùng dưới dạng chuỗi. Chẳng hạn, công cụ mô phỏng bốn khả năng độc lập: `READ`, `WRITE`, `EXECUTE` và `ADMIN`. Người dùng gõ các lệnh như `grant read`, `revoke write`, `status` hoặc `deploy`. Chương trình cần:

1. Lưu trạng thái của nhiều khả năng trong **một số nguyên** bằng các **cờ bit** (*bit flags/bitmask*).
2. Bật, tắt, kiểm tra cờ mà **không tác động đến những cờ còn lại**.
3. Nhận chuỗi lệnh, kiểm tra tham số, định tuyến đến hành động thích hợp bằng **`switch(String)`**, cú pháp được bổ sung trong Java 7 và vẫn hỗ trợ trên các JDK hiện hành.
4. Phân biệt “có **tất cả** cờ bắt buộc” với “có **ít nhất một** cờ trong nhóm”.
5. Xử lý trường hợp rỗng, sai số tham số, sai tên cờ hoặc tên lệnh; từ chối thao tác không đủ điều kiện.
6. Kiểm chứng bằng một chương trình Java chạy độc lập, bao gồm cả kết quả đầu ra.

Bài sử dụng **Java 7 language features vẫn hợp lệ hiện nay**: binary literals (`0b...`), phép toán bit và `switch` trên `String`. Để chạy thực tế, dùng JDK đang được hỗ trợ, ví dụ JDK 17 trở lên. Không cần chạy một JDK 7 đã hết vòng đời hỗ trợ.

> Đây là **mô phỏng nội bộ để học biểu diễn trạng thái**, không phải hệ thống cấp quyền thật. Trong ứng dụng bảo mật, người gọi không được tự ý `grant` quyền cho chính mình; xác thực, phân quyền và audit phải được kiểm soát ở tầng tin cậy.

## 2. Biểu diễn nhiều cờ bằng một bitmask

Một số nguyên `int` có 32 bit. Với bốn trạng thái độc lập, đặt mỗi cờ tại **một vị trí bit riêng**:

```java
private static final int READ    = 0b0001; // 1 << 0
private static final int WRITE   = 0b0010; // 1 << 1
private static final int EXECUTE = 0b0100; // 1 << 2
private static final int ADMIN   = 0b1000; // 1 << 3

private static final int ALL = READ | WRITE | EXECUTE | ADMIN;
```

Đây là **đoạn khai báo trong một class**, không phải file Java độc lập.

| Cờ | Bit thứ | Dạng nhị phân 4 bit | Giá trị thập phân |
| --- | ---: | --- | ---: |
| `READ` | 0 | `0001` | 1 |
| `WRITE` | 1 | `0010` | 2 |
| `EXECUTE` | 2 | `0100` | 4 |
| `ADMIN` | 3 | `1000` | 8 |
| `ALL` | 0–3 | `1111` | 15 |

Chọn **lũy thừa của hai** để mỗi cờ chiếm một bit không trùng. Nếu dùng `READ=1` và `WRITE=3`, kiểm tra cờ sẽ bị chồng lấn vì `3` có hai bit bật. Hãy đặt tên hằng mô tả nghiệp vụ, tránh rải số `1`, `2`, `4` khắp code.

Ví dụ `flags = READ | EXECUTE`:

```text
READ     0001
EXECUTE  0100
OR       ----
flags    0101  = 5
```

`flags` không lưu một danh sách chuỗi; nó lưu một **mẫu bit**. Có thể kết hợp nhiều cờ mà không cần thêm một biến `boolean` cho từng cờ, hữu ích cho protocol/wire format, định dạng lưu trữ đã quy ước hoặc API yêu cầu numeric masks.

## 3. Các phép toán bit phải thuộc lòng

Giả sử `flags` là số nguyên trạng thái và `bit` là một cờ hợp lệ:

| Mục tiêu | Biểu thức | Ví dụ |
| --- | --- | --- |
| **Bật** một hoặc nhiều cờ | `flags |= bit` | `0101 | 0010 = 0111` |
| **Tắt** một hoặc nhiều cờ | `flags &= ~bit` | `0111 & ~0010 = 0101` trong 4 bit thấp |
| **Đảo trạng thái** cờ | `flags ^= bit` | `0101 ^ 0001 = 0100` |
| Có **tất cả** cờ cần thiết? | `(flags & required) == required` | `0111 & 0110 == 0110` → `true` |
| Có **bất kỳ** cờ trong nhóm? | `(flags & candidates) != 0` | `0101 & 1010 != 0` → `false` |
| Có một cờ? | `(flags & READ) != 0` | `0101 & 0001` khác `0` |
| Xóa mọi cờ | `flags = 0` | `0000` |
| Chặn bit ngoài danh sách | `(flags & ~ALL) != 0` | Phát hiện các bit chưa được định nghĩa |

Cú pháp `|=` tương đương `flags = flags | bit`. `&= ~` tắt bit vì `~bit` đảo tất cả bit của kiểu `int`, giữ `1` ở mọi vị trí ngoại trừ các vị trí muốn xóa. Phần còn lại được bảo toàn khi AND. Đừng nghĩ `~READ` là một số nguyên dương 4 bit; thực tế `~` tác động toàn bộ **32 bit** của `int`.

**Điểm khác biệt quan trọng:** nếu `flags = READ` và `required = WRITE | EXECUTE`:

```java
boolean all = (flags & required) == required; // false
boolean any = (flags & required) != 0;        // false
```

Nếu `flags = WRITE`:

```java
boolean all = (flags & required) == required; // false
boolean any = (flags & required) != 0;        // true
```

Không kiểm tra nhóm quyền bắt buộc bằng `(flags & required) != 0`: phép đó chỉ yêu cầu **một** trong nhiều cờ. Ngược lại, `(flags & required) == required` khi `required=0` có kết quả toán học là `true`. Với kiểm tra “phải có quyền”, thường nên từ chối mask bằng 0 trước khi thực hiện; chương trình bên dưới chủ động áp dụng chính sách đó.

### Binary literal và toán tử dịch trái

Java hỗ trợ `0b...` từ Java 7. Có thể đặt cờ bằng `1 << index` để sinh lũy thừa hai. `1 << 3` cho giá trị `8`. Nhưng `int` có đúng 32 bit; `1 << 31` đặt bit dấu nên kết quả **âm**, còn `1 << 32` thực tế dịch 0 bit (khoảng dịch được giới hạn bởi 5 bit thấp), nên lại bằng `1`. Đối với `long`, viết `1L << index` và chỉ dùng index hợp lệ từ 0 đến 63; `1L << 63` cũng là bit dấu.

Không tự tạo cờ bằng một `index` chưa được kiểm tra từ người dùng. Với nhiều cờ hơn một số nguyên và không cần tương thích wire format, cân nhắc `EnumSet` thay vì tự quản lý bit-index.

## 4. Điều phối lệnh dựa trên String

Từ Java 7, một `switch` statement có thể nhận `String` làm selector:

```java
switch (action) {
    case "status":
        // Hiển thị trạng thái
        break;
    case "reset":
        // Xóa trạng thái
        break;
    default:
        // Lệnh không nhận diện được
}
```

Đây là **đoạn minh họa trong một phương thức có biến `action`**, chưa phải chương trình đầy đủ.

Các `case` chuỗi được so sánh theo **nội dung** của `String`, không dựa trên `==` (so sánh tham chiếu). Các nhãn `case` phải là giá trị hằng phù hợp. `switch` trên `String` phân biệt chữ hoa/thường: `"GRANT"` khác `"grant"` nếu không chuẩn hóa trước.

Trong parser dòng lệnh, nên tách:

- **Tên hành động**: `grant`, `revoke`, `has`, `status`, `deploy`, `reset`.
- **Đối số**: như `read`, `write`; có thể đổi về chữ thường theo `Locale.ROOT` cho tên lệnh ASCII, tránh phụ thuộc default locale của máy.
- **Trạng thái bitmask**: thay đổi chỉ **sau khi** toàn bộ tên lệnh, số đối số và tên cờ được xác minh hợp lệ.

Ví dụ `"  grant   WRITE  "` được làm sạch bằng `trim()` và `split("\\s+")`; command trở thành `grant` và tên cờ trở thành `write` để đối chiếu. `String.trim()`/`\\s` trong ví dụ đủ cho cú pháp lệnh ASCII; một command language có đường dẫn trích dẫn, escaping, tham số nhiều từ hoặc Unicode whitespace cần tokenizer chuyên biệt, không nên cố dùng `split` cho mọi trường hợp.

**Tránh `switch(null)`** với cú pháp `switch(String)` truyền thống: selector `null` ném `NullPointerException`. Hãy xử lý `raw == null` trước khi tách và điều phối. Các phiên bản Java mới có cú pháp switch mở rộng, nhưng `switch(String)` kiểu `case ...: break;` vẫn hợp lệ và phù hợp với nội dung bài này.

## 5. Chương trình tích hợp chạy độc lập

Để giữ ví dụ ngắn mà đủ chức năng, chương trình quản lý **một bitmask 4 cờ trong bộ nhớ** và duyệt lần lượt một kịch bản lệnh cố định. Các lệnh không đi từ input ngoài và **không phải cơ chế phân quyền production**.

Tạo tệp **`BitFlagCommandDemo.java`** đúng với tên `public class`:

```java
import java.util.Locale;

public class BitFlagCommandDemo {
    private static final int READ = 0b0001;
    private static final int WRITE = 0b0010;
    private static final int EXECUTE = 0b0100;
    private static final int ADMIN = 0b1000;
    private static final int ALL = READ | WRITE | EXECUTE | ADMIN;

    private int flags;

    private static boolean hasAll(int actual, int required) {
        return required != 0 && (actual & required) == required;
    }

    private static boolean hasAny(int actual, int candidates) {
        return (actual & candidates) != 0;
    }

    private static int flagOf(String token) {
        switch (token.toLowerCase(Locale.ROOT)) {
            case "read":    return READ;
            case "write":   return WRITE;
            case "execute": return EXECUTE;
            case "admin":   return ADMIN;
            default:        return 0;
        }
    }

    private static String names(int mask) {
        StringBuilder result = new StringBuilder();
        if ((mask & READ) != 0) result.append("READ,");
        if ((mask & WRITE) != 0) result.append("WRITE,");
        if ((mask & EXECUTE) != 0) result.append("EXECUTE,");
        if ((mask & ADMIN) != 0) result.append("ADMIN,");

        if (result.length() == 0) return "NONE";
        return result.substring(0, result.length() - 1);
    }

    private static String bits(int mask) {
        if ((mask & ~ALL) != 0) {
            throw new IllegalArgumentException("unknown bits");
        }

        return "0b" + String.format(
                Locale.ROOT, "%4s", Integer.toBinaryString(mask))
                .replace(' ', '0');
    }

    public void execute(String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            System.out.println("ERROR empty command");
            return;
        }

        String[] parts = raw.trim().split("\\s+");
        String action = parts[0].toLowerCase(Locale.ROOT);

        switch (action) {
            case "grant":
            case "revoke":
            case "has": {
                if (parts.length != 2) {
                    System.out.println(
                            "ERROR usage: " + action + " <flag>");
                    break;
                }

                int bit = flagOf(parts[1]);
                if (bit == 0) {
                    System.out.println(
                            "ERROR unknown flag: " + parts[1]);
                    break;
                }

                if ("grant".equals(action)) {
                    flags |= bit;
                    System.out.println(
                            "GRANT " + names(bit) + " -> " + bits(flags));
                } else if ("revoke".equals(action)) {
                    flags &= ~bit;
                    System.out.println(
                            "REVOKE " + names(bit) + " -> " + bits(flags));
                } else {
                    System.out.println(
                            "HAS " + names(bit) + " = " + hasAll(flags, bit));
                }
                break;
            }

            case "status":
                if (parts.length != 1) {
                    System.out.println("ERROR usage: status");
                    break;
                }
                System.out.println(
                        "STATUS " + bits(flags) + " " + names(flags));
                break;

            case "deploy":
                if (parts.length != 1) {
                    System.out.println("ERROR usage: deploy");
                    break;
                }
                boolean permitted = hasAll(flags, WRITE | EXECUTE);
                System.out.println(permitted
                        ? "DEPLOY allowed"
                        : "DEPLOY denied: needs WRITE and EXECUTE");
                break;

            case "reset":
                if (parts.length != 1) {
                    System.out.println("ERROR usage: reset");
                    break;
                }
                flags = 0;
                System.out.println("RESET " + bits(flags));
                break;

            default:
                System.out.println(
                        "ERROR unknown command: " + parts[0]);
        }
    }

    public static void main(String[] args) {
        BitFlagCommandDemo demo = new BitFlagCommandDemo();
        String[] script = {
            "status", "grant read", "grant WRITE", "status",
            "has read", "has admin", "deploy", "grant execute",
            "deploy", "revoke write", "deploy", "grant unknown",
            "grant", "status", "reset", "dance"
        };

        for (String command : script) {
            demo.execute(command);
        }

        // Phép kiểm tra "bất kỳ" trên một ví dụ độc lập với demo.flags.
        System.out.println("ANY write/admin = "
                + hasAny(WRITE, WRITE | ADMIN));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 BitFlagCommandDemo.java
java BitFlagCommandDemo
```

Kết quả đã kiểm tra với bộ biên dịch Java hiện hành:

```text
STATUS 0b0000 NONE
GRANT READ -> 0b0001
GRANT WRITE -> 0b0011
STATUS 0b0011 READ,WRITE
HAS READ = true
HAS ADMIN = false
DEPLOY denied: needs WRITE and EXECUTE
GRANT EXECUTE -> 0b0111
DEPLOY allowed
REVOKE WRITE -> 0b0101
DEPLOY denied: needs WRITE and EXECUTE
ERROR unknown flag: unknown
ERROR usage: grant <flag>
STATUS 0b0101 READ,EXECUTE
RESET 0b0000
ERROR unknown command: dance
ANY write/admin = true
```

Dòng cuối minh họa `hasAny(WRITE, WRITE | ADMIN)` bằng một **biểu thức riêng**, không phải trạng thái của `demo` sau `reset`. Nó trả `true` vì bit `WRITE` có trong nhóm ứng viên `WRITE | ADMIN`.

### Phân tích từng chặng

1. Ban đầu `flags=0000` nên `status` trả `NONE`.
2. `grant read` dùng `|= 0001` thành `0001`. `grant WRITE` được chuẩn hóa chữ thường để nhận diện và đặt thêm bit `0010`, thành `0011`. Hai flag không xóa lẫn nhau.
3. `has read` kiểm tra `(0011 & 0001)==0001` → `true`; `has admin` kiểm tra `(0011 & 1000)==1000` → `false`.
4. `deploy` yêu cầu **đồng thời** `WRITE | EXECUTE = 0110`. Ban đầu `0011 & 0110 = 0010`, không đủ `0110` nên bị từ chối.
5. `grant execute` cho trạng thái `0111`; khi đó `0111 & 0110 = 0110`, vì vậy `deploy` được cho phép.
6. `revoke write` áp dụng `&= ~0010`, đưa trạng thái về `0101`. Lần `deploy` tiếp theo lại bị từ chối dù `EXECUTE` vẫn bật.
7. `grant unknown` không ánh xạ tới bit hợp lệ; `grant` thiếu đối số và `dance` sai tên lệnh. Cả ba chỉ in lỗi, **không cập nhật trạng thái**.
8. `reset` đặt `flags=0`, bỏ tất cả cờ. Cờ `ADMIN` trong demo là **một bit độc lập**, không tự cho phép `deploy`; muốn có quy tắc “admin sở hữu mọi khả năng” phải định nghĩa nghiệp vụ rõ ràng rồi viết và kiểm thử quy tắc đó.

## 6. Tại sao điều phối String và cập nhật bitmask được tách rời?

Một bộ xử lý lệnh có ba tầng logic riêng:

```text
Chuỗi đầu vào
    |
    v
Kiểm tra null/rỗng, tách token, chuẩn hóa tên lệnh
    |
    v
switch(action) -> kiểm tra số tham số và ánh xạ tên cờ
    |
    v
Thực thi phép bit phù hợp trên trạng thái
    |
    v
Kết quả hoặc lỗi có kiểm soát
```

Việc phân tầng giúp phân biệt một **lệnh hợp lệ** với một **tham số hợp lệ**. Ví dụ `grant banana` có action `grant` nhưng cờ không tồn tại; chỉ nhìn vào tên lệnh để cập nhật trạng thái sẽ tạo lỗi khó phát hiện. Trong chương trình, `flagOf` trả `0` làm tín hiệu “không có cờ khớp”, vì các cờ thật đều khác 0. Với API lớn hơn, có thể trả `enum` hoặc `Optional` và giải quyết lỗi theo kiểu rõ ràng hơn.

`switch` không tự bảo đảm xác thực input, không giới hạn số lượng token và cũng không chặn tác vụ nguy hiểm. Điều kiện kiểm tra nằm **trước** phép thay đổi trạng thái. Với command không biết, dùng `default` để báo lỗi rõ ràng thay vì im lặng. Với các case dùng dấu hai chấm `:`, phải đặt `break`/`return` đúng chỗ: quên `break` có thể làm lệnh chảy sang case tiếp theo (*fall-through*).

Bản demo cố ý ghép ba nhãn `grant`, `revoke` và `has` vào cùng một khối, sau đó chọn phép thao tác dựa trên tên action. Đây là **fall-through có chủ ý chỉ ở các nhãn trống**, kết thúc bằng `break`. Với các nhóm lệnh lớn, nên tách thành handler có trách nhiệm riêng để giảm nhầm lẫn.

## 7. Cờ bit có tính chất gì và nên kiểm thử thế nào?

Các tính chất đại số quan trọng:

- **Bật lại cùng cờ là idempotent:** `(flags | READ) | READ == flags | READ`.
- **Tắt lại cùng cờ là idempotent:** `(flags & ~READ) & ~READ == flags & ~READ`.
- **Đảo cờ hai lần trở về trạng thái cũ:** `(flags ^ READ) ^ READ == flags`. Vì vậy `^=` là thao tác **toggle**, không dùng thay cho “bật chắc chắn” hoặc “tắt chắc chắn”.
- **Giữ các cờ khác:** bật/tắt `WRITE` không được làm thay đổi các bit `READ`/`EXECUTE`/`ADMIN`.
- **Bộ cờ hợp lệ:** `(flags & ~ALL) == 0`. Dùng kiểm tra này nếu nhận mask từ file, mạng, database hoặc API bên ngoài.
- **Yêu cầu nhiều cờ:** `hasAll(flags, WRITE | EXECUTE)` phải là `false` nếu chỉ có một trong hai. `hasAny(...)` khi đó lại có thể là `true`.

Bảng kiểm thử tối thiểu:

| Trạng thái ban đầu | Lệnh/kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| `0000` | Bật `READ` | `0001` |
| `0001` | Bật `READ` lần hai | `0001`, không đổi |
| `0001` | Bật `WRITE` | `0011` |
| `0011` | Tắt `READ` | `0010` |
| `0010` | Kiểm tra `READ | WRITE` bằng `hasAll` | `false` |
| `0010` | Kiểm tra `READ | WRITE` bằng `hasAny` | `true` |
| `0110` | Kiểm tra `WRITE | EXECUTE` bằng `hasAll` | `true` |
| `0110` | Tắt `WRITE` hai lần | `0100` |
| `0000` | Lệnh trống/sai/sai cờ | Không đổi trạng thái, báo lỗi |
| `1111` | Nhập mask có bit ngoài `ALL` | Từ chối theo quy ước hệ thống |

Bảng này là **test cases cho hành vi**, không phải các lệnh của cùng một phiên chạy nối tiếp. Khi tự viết unit test, nên tạo một instance mới cho mỗi ca và xác nhận mask/đầu ra; tránh phụ thuộc thứ tự test.

## 8. Khi nào dùng int/long, khi nào dùng EnumSet?

`int` làm bitmask thuận tiện khi cần **giá trị số cố định** trong protocol/format có quy ước, tương tác API nhận cờ bit hoặc ghi dữ liệu rất gọn. `long` cho thêm vị trí cờ nhưng vẫn bị giới hạn 64 bit và có bit dấu. Hạn chế của bitmask thủ công là khó phát hiện dùng nhầm nhóm cờ và dễ quên kiểm tra bit ngoài miền.

Với tập lựa chọn cố định **chỉ dùng trong Java code**, `EnumSet` thường dễ đọc và an toàn kiểu hơn:

```java
import java.util.EnumSet;

enum Permission {
    READ, WRITE, EXECUTE, ADMIN
}

// Đoạn sau đặt trong phương thức:
EnumSet<Permission> permissions =
        EnumSet.of(Permission.READ, Permission.WRITE);

permissions.add(Permission.EXECUTE);
boolean mayDeploy = permissions.containsAll(
        EnumSet.of(Permission.WRITE, Permission.EXECUTE));
permissions.remove(Permission.WRITE);
```

Đây là **các đoạn minh họa**, không phải một file Java độc lập. `EnumSet` được triển khai gọn và tối ưu cho các giá trị enum; nó tránh việc tự đặt shift index và đặt tên biến `int` cho từng nhóm cờ. Tuy nhiên, `EnumSet` không tự thay thế một numeric mask đã được chuẩn hóa trong giao thức ngoài; nếu cần trao đổi wire format, phải định nghĩa cách mã hóa/giải mã rõ ràng.

**Không đặt nhiều loại cờ khác nghĩa chung một int** rồi dùng toán tử bit giữa chúng: compiler không nhận biết khác biệt giữa mask “trạng thái tài liệu” và mask “quyền thao tác”. Đặt mỗi nhóm trong một wrapper/class riêng, hoặc dùng enum khi phù hợp.

## 9. Các điều kiện thực tế cần thiết trước khi mở rộng bài tập

**Nhập lệnh từ người dùng:** ví dụ cố định dùng `String[] script`. Để đọc lệnh thật từ console, có thể dùng `BufferedReader` cùng `InputStreamReader(System.in, StandardCharsets.UTF_8)` trong try-with-resources; đọc theo dòng, chặn dòng quá dài/đầu vào lạm dụng, và gọi `execute(line)`. Không tự nối chuỗi lệnh rồi đưa vào shell hoặc SQL; `switch(String)` chỉ là điều phối trong code, không phải cơ chế sandbox.

**Chuẩn hóa:** `toLowerCase(Locale.ROOT)` phù hợp với keyword kiểu ASCII đã được công bố (`grant`, `status`...). Nếu tên lệnh/đối số phân biệt chữ hoa/thường theo yêu cầu, **không** ép lowercase; viết quy tắc rõ ràng. Không dùng `==` để so nội dung `String`.

**Trạng thái dùng chung:** demo dùng `private int flags` trong một instance, chỉ truy cập tuần tự từ một thread. Nếu nhiều thread đồng thời bật/tắt cờ, biểu thức `flags |= bit` là thao tác đọc–sửa–ghi và có thể **mất cập nhật**; chỉ thêm `volatile` không làm phép toán này trở thành atomic. Hãy dùng đồng bộ hoặc `AtomicInteger` với các thao tác update phù hợp ở runtime Java hiện hành, và giữ check/modify nhất quán nếu nghiệp vụ cần.

**Lưu trữ/trao đổi:** nếu deserialize numeric mask, kiểm tra `(incoming & ~ALL) == 0` trước khi nhận. Định nghĩa phiên bản schema, ý nghĩa bit và cách xử lý unknown bits. Không tái sử dụng cùng bit cho ý nghĩa khác ở phiên bản tiếp theo; điều đó sẽ làm dữ liệu cũ bị hiểu sai.

**Bảo mật:** `grant` trong ví dụ chỉ mô phỏng phép tính, không tự động có giá trị phân quyền thực. Quyết định nhạy cảm phải dựa trên quyền được xác lập từ một nguồn tin cậy, kiểm tra ở backend, và áp dụng nguyên tắc ít đặc quyền. Không coi numeric flag đến từ client hoặc request là bằng chứng quyền hợp lệ.

**Tối ưu hóa:** nếu xử lý một bộ 4–10 flag đơn giản, chi phí giữa `switch`/`Map`/`EnumSet` thường nhỏ so với I/O. Ưu tiên tính đúng, dễ đọc, test được; không tự tối ưu theo suy đoán. Với tập lệnh ngày càng lớn, mỗi lệnh có nhiều đối số/ngữ nghĩa khác nhau, tách parser, router và handler thay vì phình một `switch` duy nhất.

## 10. Các lỗi phổ biến

1. **Đặt cờ không là lũy thừa hai:** ví dụ `READ=1`, `WRITE=3` làm hai cờ trùng bit; hãy dùng `1 << n` hoặc literal nhị phân tách biệt.
2. **Dùng `+` thay `|` để bật:** khi bật cùng cờ lần thứ hai, phép cộng làm thay đổi các bit khác; `OR` là phép đặt bit đúng.
3. **Dùng `^` để “đảm bảo cờ được bật”:** XOR chỉ đảo bit. Bật bằng `|`, tắt bằng `& ~`.
4. **Dùng `(flags & required) != 0` cho thao tác đòi mọi quyền:** biểu thức chỉ kiểm tra ít nhất một bit, dẫn đến cho phép quá mức.
5. **Không kiểm tra mặt nạ `0` hoặc unknown bits:** `hasAll(flags, 0)` bằng `true` theo phép toán đơn thuần; có thể từ chối nếu nghiệp vụ không chấp nhận yêu cầu rỗng.
6. **Quên `break` trong `switch` kiểu `case:`:** một lệnh có thể chạy thêm nhánh kế tiếp ngoài ý muốn.
7. **Không xử lý `null`:** `switch(String)` trên null có thể ném `NullPointerException`; kiểm tra trước.
8. **Tin dữ liệu lệnh đầu vào:** tên cờ, số đối số, độ dài/định dạng và quyền gọi lệnh phải được xác minh.
9. **Nhầm điều phối lệnh với authorization:** `switch` chuyển điều khiển trong code; nó không chứng minh người gọi được phép thực hiện lệnh.
10. **Nhầm shift distance:** `1 << 32` không tạo bit thứ 32 của `int` mà quay về bit 0; dùng kiểu/cấu trúc đúng và kiểm tra index.
11. **Dùng chung trạng thái mutable không đồng bộ:** có thể mất cập nhật khi nhiều thread cùng `|=` hoặc `&=`.
12. **Cho rằng `String` case-insensitive tự động:** `switch("GRANT")` không khớp `case "grant"` nếu chưa chuẩn hóa.
13. **Chạy số nguyên bit dấu mà không kiểm soát:** bit cao nhất của `int`/`long` khiến numeric mask có thể âm; điều này không làm bitwise sai nhưng cần hiểu khi lưu trữ, hiển thị và so sánh.

## 11. Bài tập tự luyện có đáp án

**Bài 1.** Với `flags = 0b0101`, chạy `flags |= WRITE`, sau đó `flags &= ~READ`. Kết quả?

**Đáp án:** `0101 | 0010 = 0111`, rồi `0111 & ~0001 = 0110`. Còn `WRITE` và `EXECUTE`.

**Bài 2.** Với `flags = 0b0010` và `required = WRITE | EXECUTE`, hai biểu thức `hasAll(flags, required)` và `hasAny(flags, required)` trả gì?

**Đáp án:** `false` và `true`. `flags` có `WRITE` nhưng thiếu `EXECUTE`.

**Bài 3.** Tại sao `grant read` hai lần không được làm cờ thành `0b0010`?

**Đáp án:** `flags |= READ` là phép OR, đặt bit 0 về 1 và các bit khác giữ nguyên. Dùng cộng hoặc XOR sẽ tạo kết quả sai khi cờ đã bật.

**Bài 4.** Lệnh `" grant    ADMIN "` được chương trình xử lý thế nào?

**Đáp án:** `trim`/`split("\\s+")` cho hai token, `grant` và `ADMIN`. `flagOf` chuẩn hóa theo `Locale.ROOT`, trả bit `ADMIN`; trạng thái được bật bit đó. Tuy nhiên, `ADMIN` **không tự suy ra** tất cả các bit khác.

**Bài 5.** Có nên cho Java client gửi `flags=0b1111` để chứng minh người dùng được phép `deploy`?

**Đáp án:** Không. Numeric mask client cung cấp là dữ liệu có thể giả mạo; backend phải lấy quyền từ nguồn tin cậy và xác thực chúng. Ví dụ chỉ minh họa biểu diễn trạng thái/luồng điều khiển.

**Bài 6.** Khi có hàng trăm trạng thái thuộc enum và không cần numeric mask trong protocol, nên cân nhắc cấu trúc gì?

**Đáp án:** `EnumSet`, vì cung cấp API tập hợp có kiểu rõ ràng, không cần quản lý vị trí bit thủ công.

### Tài liệu Java chính thức

- [Java Language Specification — toán tử bit `&`, `|`, `^` và shift](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html)
- [Java Language Specification — `switch` statement](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html)
- [Java SE API — `EnumSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/EnumSet.html)
- [Java SE API — `Locale.ROOT`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html)
