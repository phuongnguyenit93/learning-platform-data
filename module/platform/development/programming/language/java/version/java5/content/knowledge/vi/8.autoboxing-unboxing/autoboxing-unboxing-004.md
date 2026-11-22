# NullPointerException khi unboxing giá trị null

## 1. Khái niệm: null không chứa một giá trị nguyên thủy

Unboxing chuyển một tham chiếu lớp bao sang giá trị nguyên thủy tương ứng, chẳng hạn `Integer -> int` hoặc `Boolean -> boolean`.

Nếu tham chiếu lớp bao là `null`, không có đối tượng để lấy giá trị ra. Java ném `NullPointerException`:

```java
// Minh họa lỗi khi chạy.
Integer missing = null;
int count = missing;
```

Câu lệnh gán có thể trông không giống một lời gọi phương thức. Tuy nhiên, về ý nghĩa, nó phải lấy giá trị `int` từ đối tượng `Integer`, tương tự thao tác `intValue()`. Tham chiếu `null` không cung cấp được giá trị đó.

`null` không tự trở thành `0`, `false` hoặc một giá trị mặc định khác. Muốn dùng mặc định, chương trình phải có một chính sách dữ liệu rõ ràng.

Cơ chế này vẫn áp dụng trong Java hiện đại. Ví dụ thực hành dùng Java 17 trở lên.

## 2. Vì sao mã biên dịch được nhưng lỗi khi chạy?

Hai trường hợp khác nhau:

```java
// Minh họa lỗi biên dịch.
int impossible = null;
```

```java
// Minh họa lỗi runtime.
Integer possibleReference = null;
int value = possibleReference;
```

Ở đoạn đầu, `null` không thể gán trực tiếp cho kiểu nguyên thủy.

Ở đoạn sau, kiểu của biểu thức là `Integer`, nên ngôn ngữ cho phép unboxing sang `int`. Giá trị thực tế của tham chiếu tại lúc chạy lại là `null`, nên chuyển đổi thất bại.

Kiểm tra kiểu không tự chứng minh rằng mọi tham chiếu lớp bao đều khác `null`. Một hợp đồng dữ liệu có thể cần yêu cầu mạnh hơn những gì riêng kiểu `Integer` biểu đạt.

Không chỉ các biến được gán `null` tường minh mới có vấn đề. Trường đối tượng kiểu lớp bao chưa được khởi tạo và phần tử của mảng lớp bao mới tạo đều có thể mang giá trị mặc định `null`. Điều này khác với biến cục bộ chưa khởi tạo, vốn phải thỏa quy tắc gán giá trị trước khi dùng.

## 3. Những vị trí unboxing dễ bị bỏ sót

| Biểu thức minh họa | Vì sao cần unboxing? |
| --- | --- |
| `int n = boxed;` | Biến nhận cần `int` |
| `boxed + 1` | Phép cộng cần giá trị số |
| `boxed++` | Cần lấy giá trị số trước khi tăng |
| `boxed == 0` | So sánh số với toán hạng nguyên thủy |
| `if (flag)` với `Boolean flag` | Điều kiện cần `boolean` |
| Truyền `Integer` cho tham số `int` | Kiểu tham số cần giá trị nguyên thủy |
| Trả về `Integer` từ phương thức có kiểu kết quả `int` | Kết quả phải được unboxing |
| Một số biểu thức `?:` trộn lớp bao và kiểu nguyên thủy | Quy tắc kiểu của toán tử có thể yêu cầu giá trị nguyên thủy |

Ví dụ một hàm ngắn:

```java
// Phương thức minh họa, đặt bên trong một lớp.
static int next(Integer count) {
    return count + 1;
}
```

Lời gọi `next(null)` không cần sai cú pháp để gây lỗi. Phép cộng trong thân hàm phải unboxing `count`.

Một dòng có nhiều phép toán có thể chứa nhiều chỗ lấy giá trị nguyên thủy. Khi chẩn đoán lỗi, không chỉ tìm dấu chấm gọi phương thức; hãy tìm cả các chuyển đổi ngầm định.

## 4. Boolean null và điều kiện rẽ nhánh

```java
// Minh họa lỗi khi chạy.
Boolean enabled = null;

if (enabled) {
    System.out.println("enabled");
}
```

`Boolean` có ba khả năng về dữ liệu: `true`, `false`, `null`. Điều kiện `if` chỉ dùng một giá trị `boolean`, nên unboxing `null` gây lỗi.

Cả toán tử có cơ chế đoản mạch cũng cần đọc được toán hạng tương ứng trước:

```java
// Minh họa lỗi khi chạy nếu enabled là null.
if (enabled && someCondition()) {
    // ...
}
```

Đoản mạch không cứu được việc unboxing toán hạng bên trái. Nếu cần kiểm tra khác `null` trước:

```java
// Minh họa hợp lệ về xử lý null.
if (enabled != null && enabled) {
    System.out.println("enabled");
}
```

Toán hạng phải chỉ được đánh giá sau khi vế trái xác nhận tham chiếu khác `null`.

Một cách khác khi hợp đồng là “chỉ true mới bật”:

```java
// Minh họa.
boolean active = Boolean.TRUE.equals(enabled);
```

Kết quả là `false` khi `enabled` là `null`. Đây là quyết định gộp trạng thái thiếu vào “không bật”; không dùng cách này nếu ứng dụng cần phân biệt “false” với “chưa cấu hình”.

## 5. Toán tử ba ngôi có thể unboxing trước khi gán cho lớp bao

Tình huống dễ gây bất ngờ:

```java
// Minh họa lỗi khi chạy.
Integer missing = null;
boolean chooseMissing = true;

Integer selected = chooseMissing ? missing : 0;
```

Dù biến nhận là `Integer`, hai nhánh cụ thể `Integer` và `int` khiến biểu thức điều kiện số trong ví dụ được xử lý với kiểu `int`. Khi chọn nhánh `missing`, nó phải unboxing `null` trước khi có thể boxing kết quả để gán lại cho `Integer`.

Việc biến nhận là lớp bao không tự bảo vệ mọi biểu thức bên phải.

Nếu ý định là giữ lại tham chiếu có thể thiếu, hai nhánh lớp bao cùng kiểu có thể biểu đạt đúng hơn:

```java
// Minh họa; không cần unboxing nhánh missing.
Integer selected =
        chooseMissing ? missing : Integer.valueOf(0);
```

Với `chooseMissing = true`, kết quả là `null`. Tuy nhiên, nếu sau đó gán `selected` cho `int`, nguy cơ unboxing vẫn còn.

Nếu ý định là thay dữ liệu thiếu bằng `0`, kiểm tra sự thiếu trực tiếp:

```java
// Minh họa khi nghiệp vụ cho phép mặc định 0.
int selected = missing == null ? 0 : missing;
```

Khi `missing` là `null`, nhánh `0` được chọn; nhánh unboxing `missing` không được đánh giá.

Không suy luận rằng mọi biểu thức `?:` có lớp bao đều unboxing. Phải xét đúng kiểu của các nhánh và kiểu biểu thức theo quy tắc Java.

## 6. Map.get: nơi null thường đi vào phép tính

```java
// Minh họa lỗi khi chạy; cần import HashMap và Map.
Map<String, Integer> counts = new HashMap<>();
int count = counts.get("missing");
```

Không có khóa `"missing"`, nên `get` trả về `null`. Phép gán sang `int` mới là chỗ cần unboxing.

Với một map cho phép giá trị `null`, còn có trường hợp khóa tồn tại nhưng được ánh xạ tới `null`:

```java
// Minh họa trong một phương thức.
counts.put("explicit", null);
Integer value = counts.get("explicit");
```

Nếu cần phân biệt “không có khóa” với “có khóa nhưng giá trị thiếu”, phải xét hợp đồng map và có thể dùng `containsKey`. Chỉ nhận được `null` từ `get` chưa đủ phân biệt hai trạng thái ấy.

### getOrDefault không phải toán tử thay mọi null

```java
// Minh họa với HashMap như trên.
int absent = counts.getOrDefault("missing", 0);
int explicit = counts.getOrDefault("explicit", 0);
```

Dòng đầu nhận mặc định vì không có ánh xạ cho khóa.

Dòng thứ hai vẫn có thể ném `NullPointerException`: khóa tồn tại và ánh xạ tới `null`, nên kết quả trả về là `null`, không phải mặc định `0`.

Nếu hợp đồng thực sự gộp cả hai trạng thái vào `0`, có thể xử lý kết quả:

```java
// Minh họa; cần import java.util.Objects.
int value = Objects.requireNonNullElse(counts.get("explicit"), 0);
```

Đây là chính sách khác với “chỉ dùng mặc định khi không có khóa”.

## 7. Chọn cách xử lý theo ý nghĩa dữ liệu

### 7.1. Giá trị là bắt buộc: kiểm tra sớm

```java
// Phương thức minh họa; cần import java.util.Objects.
static int requireCount(Integer raw) {
    return Objects.requireNonNull(raw, "count is required");
}
```

Nếu `raw` là `null`, phương thức từ chối ở vị trí có thông điệp rõ. Nếu khác `null`, giá trị được unboxing để trả về.

Mục tiêu không phải che ngoại lệ bằng giá trị mặc định, mà làm hợp đồng “bắt buộc có dữ liệu” hiện rõ và phát hiện vi phạm gần nơi nhận dữ liệu.

### 7.2. Thiếu dữ liệu là hợp lệ: giữ trạng thái và rẽ nhánh

```java
// Minh họa trong một phương thức.
Integer raw = counts.get(key);

if (raw == null) {
    System.out.println("missing");
} else {
    int value = raw;
    System.out.println(value);
}
```

Đọc một lần vào biến cục bộ giúp theo dõi đúng giá trị vừa kiểm tra, thay vì rải nhiều lời gọi lấy dữ liệu trong cùng biểu thức.

### 7.3. Có mặc định được nghiệp vụ cho phép: dùng rõ ràng

```java
// Minh họa; cần import java.util.Objects.
int count = Objects.requireNonNullElse(raw, 0);
```

`requireNonNullElse` trả về đối số đầu nếu khác `null`, nếu không thì dùng giá trị mặc định khác `null`. Ở đây `0` được boxing ở lời gọi phù hợp rồi kết quả được unboxing sang `int`.

Đừng truyền mặc định có thể `null` rồi cho rằng phương thức sẽ luôn tạo ra một giá trị nguyên thủy an toàn.

Đặt tên hoặc ghi rõ chính sách mặc định ở ranh giới xử lý; tránh âm thầm đổi một lỗi thiếu dữ liệu thành số hợp lệ nhưng sai ý nghĩa.

## 8. So sánh nào có unboxing, so sánh nào không?

```java
// Minh họa trong một phương thức.
Integer missing = null;

boolean isMissing = missing == null;
```

So sánh với literal `null` kiểm tra tham chiếu, không cần lấy giá trị `int`.

Ngược lại:

```java
// Minh họa lỗi khi chạy.
boolean isZero = missing == 0;
```

Đây là so sánh với giá trị nguyên thủy, cần unboxing.

Nếu mục đích là kiểm tra giá trị bao gồm trường hợp thiếu:

```java
// Minh họa; cần import java.util.Objects.
boolean isZero = Objects.equals(missing, Integer.valueOf(0));
```

Kết quả là `false` khi `missing` là `null`, không gây lỗi unboxing. Cách này không tự biến “thiếu” thành số `0`; nó chỉ trả lời hai đối tượng có bằng nhau theo quy tắc tương ứng hay không.

Không dùng `==` giữa hai tham chiếu lớp bao để thay so sánh giá trị. Đó là một vấn đề khác với việc phát hiện `null`.

## 9. Chương trình đầy đủ

Lưu vào `NullUnboxingDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class NullUnboxingDemo {
    static void observe(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ":OK");
        } catch (NullPointerException ex) {
            System.out.println(label + ":NPE");
        }
    }

    public static void main(String[] args) {
        Integer missing = null;
        Boolean absentFlag = null;
        boolean chooseMissing = true;

        Map<String, Integer> counts = new HashMap<>();
        counts.put("explicit", null);

        observe("assignment", () -> {
            int value = missing;
            System.out.println(value);
        });

        observe("arithmetic", () -> {
            int value = missing + 1;
            System.out.println(value);
        });

        observe("comparison", () -> {
            boolean value = missing == 0;
            System.out.println(value);
        });

        observe("boolean", () -> {
            if (absentFlag) {
                System.out.println("enabled");
            }
        });

        observe("conditional", () -> {
            Integer value = chooseMissing ? missing : 0;
            System.out.println(value);
        });

        observe("map-absent", () -> {
            int value = counts.get("missing");
            System.out.println(value);
        });

        observe("map-explicit-null", () -> {
            int value = counts.getOrDefault("explicit", 0);
            System.out.println(value);
        });

        int fallback = Objects.requireNonNullElse(missing, 0);
        System.out.println("fallback=" + fallback);

        boolean enabled = Boolean.TRUE.equals(absentFlag);
        System.out.println("enabled=" + enabled);

        Integer kept = chooseMissing ? missing : Integer.valueOf(0);
        System.out.println("keptNull=" + (kept == null));

        int absentDefault = counts.getOrDefault("missing", 0);
        System.out.println("absentDefault=" + absentDefault);

        int explicitDefault =
                Objects.requireNonNullElse(counts.get("explicit"), 0);
        System.out.println("explicitDefault=" + explicitDefault);

        System.out.println("isZero="
                + Objects.equals(missing, Integer.valueOf(0)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NullUnboxingDemo.java
java NullUnboxingDemo
```

Stdout chính xác:

```text
assignment:NPE
arithmetic:NPE
comparison:NPE
boolean:NPE
conditional:NPE
map-absent:NPE
map-explicit-null:NPE
fallback=0
enabled=false
keptNull=true
absentDefault=0
explicitDefault=0
isZero=false
```

Hàm `observe` bắt ngoại lệ chỉ để quan sát độc lập nhiều tình huống trong một lần chạy. Đây không phải mẫu xử lý dữ liệu thiếu nên sao chép vào mã nghiệp vụ.

Không in nguyên thông báo lỗi của JVM vào stdout kỳ vọng vì cách mô tả chi tiết có thể khác giữa các phiên bản hoặc cấu hình. Chương trình dùng nhãn cố định để kiểm tra đúng loại lỗi và vị trí minh họa.

Các dòng cuối cho thấy ba ý định khác nhau:

- Chọn mặc định `0` hoặc `false` khi hợp đồng cho phép.
- Giữ `null` dưới kiểu tham chiếu khi cần bảo toàn trạng thái thiếu.
- So sánh giá trị một cách không cần unboxing.

## 10. Cách chẩn đoán khi gặp lỗi

1. Đọc vị trí trong stack trace và xác định biểu thức gây lỗi.
2. Tìm mọi toán hạng lớp bao trong biểu thức, kể cả giá trị trả về từ `get`, lời gọi phương thức hoặc nhánh `?:`.
3. Xác định thao tác nào đang cần kiểu nguyên thủy.
4. Tách biểu thức thành biến cục bộ để kiểm tra giá trị tham chiếu trước bước chuyển đổi.
5. Theo ngược nơi dữ liệu trở thành `null`: thiếu khóa, phần tử mảng chưa gán, trường chưa khởi tạo hay kết quả API.
6. Chọn chính sách bắt buộc có, cho phép thiếu hoặc mặc định có ý nghĩa.
7. Kiểm tra cả dữ liệu có giá trị, `null`, `0`, `false` và trường hợp có khóa nhưng ánh xạ tới `null` nếu dùng map cho phép điều đó.

Không chỉ đổi biến nhận từ `int` sang `Integer` rồi kết luận đã sửa xong. Một phép tính hoặc nhánh điều kiện tiếp theo có thể lại cần unboxing.

Cũng không bắt toàn bộ `NullPointerException` quanh một khối nghiệp vụ rồi trả về `0`: cách đó có thể che các lỗi truy cập `null` khác, không chỉ lỗi unboxing đang muốn xử lý.

## 11. Những lỗi thường gặp

- Cho rằng mọi biến kiểu lớp bao đều tự có giá trị mặc định như kiểu nguyên thủy.
- Chỉ tìm các lời gọi `intValue()` viết tường minh mà bỏ qua chuyển đổi tự động.
- Nghĩ đoản mạch luôn tránh được lỗi dù vế trái đã là một `Boolean` thiếu.
- Nghĩ biến nhận `Integer` bảo vệ được mọi biểu thức ba ngôi ở bên phải.
- Dùng `getOrDefault` để mong thay cả ánh xạ hiện có tới `null`.
- Gộp trạng thái thiếu với `0` hoặc `false` mà chưa xét ý nghĩa nghiệp vụ.
- Dùng thông báo chi tiết của một JVM làm hợp đồng cố định cho logic ứng dụng.

## 12. Tự kiểm tra

1. Vì sao `Integer x = null; int y = x;` biên dịch được nhưng `int y = null;` không biên dịch?
2. Liệt kê ít nhất ba vị trí có thể unboxing mà không viết `intValue()`.
3. So sánh `missing == null`, `missing == 0` và `Objects.equals(missing, 0)`.
4. Giải thích kết quả của hai biểu thức `choose ? missing : 0` và `choose ? missing : Integer.valueOf(0)` với `choose = true`.
5. Một `HashMap<String, Integer>` có khóa `"x"` ánh xạ tới `null`. Vì sao `int n = map.getOrDefault("x", 0)` vẫn lỗi?
6. Viết một hàm nhận `Integer` bắt buộc có giá trị và một hàm khác cho phép thiếu với mặc định được mô tả rõ.
7. Một cờ cấu hình có ba trạng thái. Khi nào `Boolean.TRUE.equals(flag)` phù hợp, khi nào nó làm mất thông tin cần thiết?

## Tài liệu đối chiếu

- [Java Language Specification — Unboxing Conversion (§5.1.8)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.8): lỗi khi tham chiếu cần unboxing là `null`.
- [Java Language Specification — Conditional Operator (§15.25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.25): kiểu của biểu thức ba ngôi.
- [Java API — Map.getOrDefault](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#getOrDefault(java.lang.Object,V)): mặc định khi không có ánh xạ cho khóa.
- [Java API — Objects.requireNonNullElse](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html#requireNonNullElse(T,T)): chọn giá trị khác `null` theo hợp đồng.
