# 7.8. Xử lý char[], clearPassword và giới hạn của việc xóa dữ liệu nhạy cảm trên JVM

## 1. Vấn đề cần giải quyết: vòng đời mật khẩu trong bộ nhớ

Mật khẩu (password), passphrase, mã PIN hoặc nguyên liệu dùng để dẫn xuất khóa thường chỉ cần tồn tại trong bộ nhớ trong một khoảng thời gian ngắn: nhận từ người dùng, dùng để xác minh hoặc dẫn xuất khóa, rồi không cần giữ dạng rõ nữa. Trên Java/JVM, vấn đề không chỉ là **không log mật khẩu** mà còn là cách đại diện dữ liệu và **ai sở hữu từng bản sao**.

Ba mục tiêu thực tế:

1. **Giảm thời gian lưu trữ plaintext password:** giải phóng/ghi đè những bộ đệm có thể kiểm soát ngay khi hoàn thành công việc.
2. **Hạn chế tạo bản sao ngoài ý muốn:** đặc biệt là `String`, chuỗi được concat, buffer của encoder, biểu mẫu, object của thư viện, bản sao được trả từ API.
3. **Hiểu giới hạn:** thao tác xoá trên một `char[]` hoặc gọi `PBEKeySpec.clearPassword()` **không chứng minh** rằng mọi dấu vết mật khẩu trong tiến trình JVM, bộ nhớ vật lý, heap dump, swap, snapshot hay thư viện native đã biến mất.

Trong JCA/JCE, `char[]` và `javax.crypto.spec.PBEKeySpec` là các công cụ giúp kiểm soát *một phần* vòng đời mật khẩu. Đây là một biện pháp giảm thiểu rủi ro, **không phải cam kết xoá bí mật tuyệt đối**.

## 2. Vì sao ưu tiên char[] thay vì String cho mật khẩu dạng rõ?

### 2.1. String không có API xoá từng ký tự

`String` là immutable. Sau khi tạo `String password`, ứng dụng không có API công khai để ghi đè đáng tin cậy các byte/ký tự do `String` lưu trữ. Việc gán `password = null` chỉ bỏ một reference; thời điểm thu gom rác không xác định, và bộ nhớ cũ có thể còn dấu vết cho đến khi được tái sử dụng hoặc bị ghi đè. `String` có thể tồn tại lâu hơn dự kiến qua log, exception, cache, stack trace, request object, serializer hoặc thao tác nối chuỗi.

`char[]` thì mutable: ứng dụng có thể gọi:

```java
Arrays.fill(password, '\0');
```

Điều này **ghi giá trị NUL vào các phần tử của chính mảng `password`**, khi phép ghi được thực thi. Nó hỗ trợ hạn chế một số bản sao ở heap mà ứng dụng đang sở hữu.

| Tiêu chí | `String` | `char[]` |
| --- | --- | --- |
| Có thể sửa trực tiếp nội dung bằng API công khai? | Không | Có, dùng `Arrays.fill` hoặc tự đặt từng phần tử |
| Có thể chủ động xoá buffer do mình sở hữu? | Không bảo đảm bằng API chuẩn | Có thể yêu cầu ghi đè buffer cụ thể, với giới hạn của JVM |
| Có thể bị copy sang nhiều nơi? | Có | Có |
| Có bảo đảm xóa mọi dấu vết trong RAM/heap? | Không | **Không** |
| Dùng trực tiếp với `PBEKeySpec`? | Không; phải tạo `char[]` | Có |

**Lưu ý quan trọng:** `char[]` không “an toàn tuyệt đối” hoặc “được JVM bảo vệ bí mật”. Nó chỉ cho phép yêu cầu sửa nội dung một mảng cụ thể. Các bản sao khác không được xóa chỉ vì ta đã sửa mảng ban đầu.

### 2.2. Một số thao tác nên tránh

```java
// Ví dụ lỗi khi xử lý mật khẩu thật:
String immutable = new String(passwordChars);  // Tạo bản sao String khó chủ động xóa.
String text = String.valueOf(passwordChars);    // Cũng tạo String.
String logLine = "password=" + new String(passwordChars);
System.out.println(passwordChars);             // Không dùng để hiển thị bí mật.
```

Đây là **đoạn mã minh họa các anti-pattern**, không phải chương trình hoàn chỉnh. `String.valueOf(char[])` tạo `String` mới chứa ký tự; `System.out.println(char[])` cũng có thể in nội dung qua overload dành cho `char[]`, do đó **không log bất kỳ char array mật khẩu nào**. Thận trọng với `Arrays.toString(passwordChars)`, debugger/watch expression, metrics labels, log structured fields và message của exception.

Cũng nên tránh chuyển mật khẩu sang `StringBuilder`/`StringBuffer` chỉ để tiếp tục xử lý: chúng có bộ đệm riêng và không tự trở thành cơ chế zeroization đáng tin cậy. Ngược lại, nếu framework đầu vào **đã** tạo `String`, việc gọi `string.toCharArray()` chỉ tạo thêm mảng; **không xoá được String nguồn**.

## 3. Quyền sở hữu dữ liệu: một mật khẩu có thể có nhiều bản sao

Xét luồng đơn giản:

```text
Nguồn nhập (terminal / UI / HTTP framework)
   |
   v
char[] callerPassword  -----------------------------+
   |                                                |
   | new PBEKeySpec(callerPassword, ...)             | Arrays.fill(callerPassword, '\0')
   v                                                | chỉ xóa mảng bên gọi
PBEKeySpec: bản sao nội bộ                         <----+
   |
   | getPassword()
   v
char[] trả về: một bản sao mới
   |
   +-- SecretKeyFactory / provider tạo dữ liệu KDF trung gian
   +-- SecretKey và có thể có byte[] từ getEncoded()
   +-- heap, native provider, stack, log, snapshot (tùy hệ thống)
```

**Mỗi mũi tên copy là một vùng phải đánh giá riêng.** Xóa `callerPassword` không tự xóa vùng nhớ trong `PBEKeySpec`. Xóa `PBEKeySpec` không tự xóa những `char[]` đã trả từ `getPassword()` hay những byte array của khóa dẫn xuất. Xóa `byte[]` mã hóa đầu ra không có nghĩa đối tượng `SecretKey` hoặc provider đã xóa bản sao của chúng.

Đây là lý do không nên thiết kế phương thức nhận password mà âm thầm giữ lại mảng do caller sở hữu hoặc đưa vào cache. Cần xác định rõ: caller hay callee chịu trách nhiệm xóa, có copy hay không, thời điểm có thể xóa và thành phần nào không kiểm soát được.

## 4. PBEKeySpec: bản sao của password và clearPassword()

`javax.crypto.spec.PBEKeySpec` dùng để cung cấp password và tùy chọn salt, iteration count, key length cho các thuật toán *Password-Based Encryption/Key Derivation* (PBE/KDF) thông qua `SecretKeyFactory`.

Ví dụ tạo spec:

```java
PBEKeySpec spec = new PBEKeySpec(passwordChars, salt, iterations, 256);
```

Chữ ký tương ứng là `PBEKeySpec(char[] password, byte[] salt, int iterationCount, int keyLength)`; `keyLength` tính bằng **bit**, không phải byte.

### 4.1. Constructor copy dữ liệu

`PBEKeySpec` tạo **bản sao riêng của password** mà ứng dụng chuyển vào. Vì vậy:

- Sửa hoặc `Arrays.fill(passwordChars, '\0')` sau khi tạo spec **không xóa** password trong spec.
- Điều này hữu ích để tránh thay đổi ngoài ý muốn khi KDF đang chạy, nhưng cũng tạo thêm vùng plaintext password trong bộ nhớ.
- Spec có API xoá **bản sao của chính nó**, không có quyền tự động xoá mọi mảng bên ngoài.

Salt cũng được sao chép khi lưu vào spec; `getSalt()` trả một bản sao. Salt thường **không bí mật**, phải lưu cùng thông tin dẫn xuất khi cần xác minh lại, nhưng tính unique và random quan trọng. Không cần đối xử với salt như password.

### 4.2. getPassword() trả bản sao, không trao quyền sở hữu nội bộ

`spec.getPassword()` trả một `char[]` **mới** chứa password mà spec đang lưu. Nếu gọi lặp nhiều lần, ứng dụng có thể tạo nhiều bản sao nhạy cảm mà không nhận ra.

```java
char[] returnedCopy = spec.getPassword();
try {
    // Nếu thật sự cần nội dung, dùng càng ngắn càng tốt.
} finally {
    Arrays.fill(returnedCopy, '\0');
}
```

Đây là đoạn mã minh họa; `spec` đã được tạo trước đó. Việc xoá `returnedCopy` **không** xoá bản sao nội bộ của spec và không xoá mảng gốc. Tránh gọi `getPassword()` chỉ để log, debug, so sánh không cần thiết hoặc kiểm tra độ dài.

### 4.3. clearPassword() tác động vào đâu?

`spec.clearPassword()` yêu cầu xóa bản sao password **được lưu bên trong PBEKeySpec**. Theo hợp đồng API Java, sau khi clear, `getPassword()` sẽ ném `IllegalStateException`.

Điều `clearPassword()` **không làm**:

- Không sửa mảng `passwordChars` do caller truyền vào.
- Không tìm và sửa các bản sao `char[]` do `getPassword()` đã trả trước đó.
- Không xóa `String` nếu framework đã tạo String trước đó.
- Không bảo đảm xóa password bytes tạm do `SecretKeyFactory`/provider/native code tạo ra.
- Không xóa material trong `SecretKey` được KDF trả về và không tự hủy byte[] do `getEncoded()` trả về.
- Không hứa dọn sạch heap dump, CPU register, swap, OS page cache, core dump, backup/snapshot.

**Thứ tự sử dụng:** tạo `PBEKeySpec` → dùng nó để tạo key/derived bytes → gọi `clearPassword()` trong `finally`. **Đừng clear spec trước khi `SecretKeyFactory.generateSecret(spec)` nếu vẫn cần password để dẫn xuất khóa.**

Nếu dùng cùng một spec qua nhiều lần, cần giới hạn vòng đời; tốt nhất chỉ tạo khi cần và đóng “cửa sổ tồn tại” ngay sau công việc. Sau `clearPassword()`, phải tạo spec mới bằng password còn hợp lệ nếu muốn thực hiện derivation khác, không được tự mong spec tái sử dụng nội dung đã xóa.

### 4.4. So sánh API thường bị nhầm

| API/Thao tác | Đối tượng bị tác động | Điều **không** được suy ra |
| --- | --- | --- |
| `Arrays.fill(charArray, '\0')` | Phần tử của đúng `charArray` | Không xóa những bản sao khác, không bảo đảm phần cứng/RAM đã được tẩy sạch |
| `PBEKeySpec.clearPassword()` | Bản sao password nội bộ của spec | Không xoá caller `char[]`, array trả từ getPassword, khóa dẫn xuất |
| `PBEKeySpec.getPassword()` | Tạo và trả **bản sao** mới | Không phải reference trực tiếp để xóa nội bộ spec |
| `Arrays.fill(keyBytes, (byte) 0)` | Byte array cụ thể | Không xóa key material trong object/provider khác |
| `password = null` | Reference cục bộ | Không có hợp đồng xóa nội dung trong heap ngay |
| `System.gc()` | Chỉ là yêu cầu/hint cho GC | Không phải API zeroization, không bảo đảm chạy/xóa đúng lúc |

## 5. Demo Java 17+ chạy độc lập và stdout đã xác minh

Bài demo chứng minh chính xác ba tình huống: một mảng do caller sở hữu, bản sao password qua `PBEKeySpec.getPassword()`, và password nội bộ bị vô hiệu hóa sau `clearPassword()`. Chương trình còn tạo derived key bằng `PBKDF2WithHmacSHA256` để cho thấy spec vẫn hoạt động dù caller đã zero mảng gốc.

**Chú ý:** chuỗi ký tự cố định trong mã chỉ phục vụ ví dụ có kết quả xác định, **không phải mật khẩu thật**. Giá trị `10_000` iterations là cấu hình minh họa cú pháp và tốc độ chạy, **không** phải thông số an toàn production. Sản phẩm cần lựa chọn thuật toán và chi phí dẫn xuất phù hợp theo hướng dẫn hiện hành, benchmark và threat model.

Tạo file `PasswordMemoryDemo.java`:

```java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordMemoryDemo {
    private static boolean allZero(char[] data) {
        for (char c : data) {
            if (c != '\0') return false;
        }
        return true;
    }

    public static void main(String[] args) throws Exception {
        // Fixed characters for a repeatable DEMO; never hardcode real passwords.
        char[] entered = {'d', 'e', 'm', 'o', '-', 'o', 'n', 'l', 'y'};
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);

        PBEKeySpec spec = null;
        char[] fromSpec = null;
        byte[] keyBytes = null;
        try {
            spec = new PBEKeySpec(entered, salt, 10_000, 256);
            fromSpec = spec.getPassword(); // A separate copy; wipe it too.
            System.out.println("Separate returned copy: " + (fromSpec != entered));

            Arrays.fill(entered, '\0'); // Clear caller-owned array.
            System.out.println("Caller cleared: " + allZero(entered));
            System.out.println("Spec copy still held password: " +
                    !allZero(fromSpec));

            Arrays.fill(fromSpec, '\0');
            fromSpec = null;

            SecretKey derived = SecretKeyFactory
                    .getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec);
            keyBytes = derived.getEncoded(); // Another sensitive buffer.
            System.out.println("Derived key size: " + keyBytes.length + " bytes");

            spec.clearPassword(); // Wipes internal password copy.
            boolean unavailable = false;
            try {
                spec.getPassword();
            } catch (IllegalStateException expected) {
                unavailable = true;
            }
            System.out.println("Spec inaccessible after clear: " + unavailable);
        } finally {
            if (fromSpec != null) Arrays.fill(fromSpec, '\0');
            if (keyBytes != null) Arrays.fill(keyBytes, (byte) 0);
            Arrays.fill(entered, '\0');
            if (spec != null) spec.clearPassword();
        }
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac PasswordMemoryDemo.java
java PasswordMemoryDemo
```

Stdout chính xác:

```text
Separate returned copy: true
Caller cleared: true
Spec copy still held password: true
Derived key size: 32 bytes
Spec inaccessible after clear: true
```

**Giải thích từng dòng:**

1. `spec = new PBEKeySpec(entered, salt, ...)` tạo bản sao nội bộ; `fromSpec = spec.getPassword()` tạo **một bản sao nữa**, khác reference với `entered`.
2. `Arrays.fill(entered, '\0')` làm mọi phần tử trong mảng caller bằng NUL. Thao tác này **không** làm thay đổi nội dung `fromSpec` đã copy trước đó; đó là lý do dòng `Spec copy still held password: true`.
3. Ta chủ động xóa mảng `fromSpec` ngay sau khi dùng. Spec vẫn giữ bản sao nội bộ để `SecretKeyFactory.generateSecret(spec)` có thể hoàn thành dẫn xuất.
4. Key length 256 **bit** tương ứng `32 bytes` từ `derived.getEncoded()` trong demo này. Byte array `keyBytes` cũng nhạy cảm, nên được `Arrays.fill` trong `finally`.
5. `spec.clearPassword()` xóa password nội bộ và các lời gọi `getPassword()` sau đó bị từ chối bằng `IllegalStateException` theo API.
6. `finally` bảo đảm gọi dọn dẹp trên các mảng đang sở hữu và spec ngay cả khi KDF hoặc bước khác ném exception. Nó **không** hứa xoá `SecretKey derived` hoặc các bản sao nội bộ của provider/JVM.

**Đừng đọc sai demo:** Kết quả `Caller cleared: true` chỉ kiểm tra **các phần tử của đúng một mảng trong ngữ cảnh chạy hiện tại**. Nó không phải phép đo chứng minh heap, native memory hoặc hệ điều hành không còn password. Việc chúng ta không in password/key cũng là chủ ý.

## 6. Xây dựng luồng nhập và xử lý password đúng hơn

### 6.1. Console.readPassword() cung cấp char[] (khác readLine())

`java.io.Console.readPassword(...)` hỗ trợ đọc ký tự mật khẩu (thường không echo ra màn hình) và trả về `char[]`. Đây là lựa chọn tốt cho ứng dụng CLI khi có interactive console.

Ví dụ **đoạn mã minh họa**, không phải một chương trình Java độc lập:

```java
Console console = System.console();
if (console == null) {
    throw new IllegalStateException("Interactive console unavailable");
}
char[] password = console.readPassword("Password: ");
if (password == null) {
    throw new IllegalStateException("End of input");
}
try {
    // Dùng password ngắn hạn với PBEKeySpec/SecretKeyFactory.
} finally {
    Arrays.fill(password, '\0');
}
```

Cần import `java.io.Console` và `java.util.Arrays`. `System.console()` có thể trả `null` khi chạy trong IDE, một số môi trường CI hoặc khi stdin/stdout được redirect; **không** tự động fallback sang `Scanner.nextLine()` mà không ý thức rằng cách đó tạo `String` và có thể echo/input handling khác.

Đừng làm `new String(console.readPassword())`: đoạn code đó tạo String dạng rõ và còn làm mất reference tới char[] vừa đọc nên không thể chủ động xóa mảng gốc.

### 6.2. JPasswordField và UI

Với Swing, `JPasswordField.getPassword()` trả `char[]` để tránh phải yêu cầu một String công khai. Sau khi sử dụng, `Arrays.fill(password, '\0')` đối với chính array nhận được và xóa nội dung trường UI theo chính sách (ví dụ khi form kết thúc). Không suy ra các bước đó đã xóa mọi bản sao từ UI document, clipboard, accessibility tooling, event queue hoặc desktop/swap. Không tự ý copy password vào clipboard hay đặt vào tooltip/exception.

### 6.3. Dữ liệu đã qua HTTP/JSON framework

Phần lớn API nhận JSON/web form thường đi qua decoder, request parser và các thư viện có thể tạo `String` hoặc byte buffer. Khi code ứng dụng nhận được `String password`, việc chuyển sang `password.toCharArray()` chỉ giúp bạn **quản lý mảng mới**; nó không điều khiển bộ nhớ giữ String ban đầu hoặc các bản sao của framework.

Cần đánh giá đường đi dữ liệu **từ lớp nhận request**, tắt log/trace chứa secret, cấu hình masking trong observability, giới hạn thời gian giữ request object và không đưa password vào session/cache/message queue ngoài nhu cầu. Không quảng cáo rằng chỉ thay DTO field `String` thành `char[]` là đã giải quyết zeroization.

## 7. Các bản sao nhạy cảm thường không nhìn thấy

| Nguồn sao chép | Vì sao có thể còn password? | Điều ứng dụng có thể làm |
| --- | --- | --- |
| `PBEKeySpec` constructor | Chủ động copy password để giữ nội dung dùng cho KDF | `clearPassword()` trong `finally` |
| `PBEKeySpec.getPassword()` | Trả về một array mới | Tránh gọi nếu không cần; xóa array đã nhận |
| `String`, nối chuỗi, formatter, logging | Immutable/copy, không có hợp đồng wipe | Tránh tạo và tuyệt đối không log dạng rõ |
| Charset/encoder và `byte[]` trung gian | Chuyển UTF-16 char sang bytes để mã hóa/KDF | Quản lý byte[] do mình tạo, `Arrays.fill(..., (byte)0)` |
| `SecretKeyFactory` và JCE provider | KDF có thể tạo bản sao/working buffers/private state | Giảm vòng đời object; kiểm tra API/provider, không hứa xóa được tất cả |
| `SecretKey.getEncoded()` | Thường trả mảng byte chứa key material mới; có thể `null` với khóa không export được | Wipe bản sao byte[] do caller sở hữu, tránh lấy key bytes nếu không cần |
| Heap dump, core dump, crash report | Snapshot có thể ghi lại object/buffer chưa xóa | Hạn chế quyền dump, giữ file dump an toàn, tránh dump môi trường production nếu không cần |
| Swap, hibernation, VM/container snapshot | OS/hạ tầng có thể ghi trang nhớ ra thiết bị lưu trữ | Chính sách bảo vệ host, swap/dump và ổ đĩa; threat model phù hợp |
| Native code/HSM/KMS/client library | Dữ liệu có thể ở ngoài heap và ngoài khả năng `Arrays.fill` của Java | Chọn provider/API với contract bảo vệ khóa rõ ràng; đừng mặc định mọi key bị xóa |

Một số key object có API `Destroyable.destroy()` hoặc triển khai đặc thù của provider. Nhưng **không được suy ra** rằng mọi `SecretKey` đều có cơ chế xóa vật liệu khóa đáng tin cậy, hỗ trợ destroy thành công hoặc dọn các bản sao đã từng tạo. Hãy đọc tài liệu của provider, kiểm tra hành vi và thiết kế hạn chế export bí mật.

## 8. Giới hạn căn bản của “xóa bộ nhớ” trên JVM

### 8.1. GC không phải công cụ zeroization

**Garbage Collection (GC)** có nhiệm vụ quản lý đối tượng không còn tham chiếu, không có hợp đồng đảm bảo ghi đè sạch mọi vùng nhớ ngay khi `password = null` hoặc `System.gc()`. `System.gc()` cũng chỉ là một yêu cầu; ứng dụng không có quyền yêu cầu JVM đi qua mọi vùng RAM và loại bỏ dấu vết bí mật.

JVM có thể di chuyển/copy object trong quá trình GC, để lại các vùng nhớ trước đó cho tới khi được ghi đè; trên nhiều hệ thống còn có dump/snapshot bên ngoài heap mà code Java không kiểm soát. Điều này làm cho “tôi đã fill array” khác với “không còn bản sao ở bất kỳ đâu”.

### 8.2. Trình biên dịch và tối ưu hóa

JIT/compiler có thể áp dụng các tối ưu hóa, ví dụ loại bỏ các phép ghi mà nó đánh giá không có ảnh hưởng quan sát được theo ngữ nghĩa chương trình. Không nên coi một `Arrays.fill` được viết ở source là **bảo đảm mật mã** rằng byte ở mọi cấp bộ nhớ chắc chắn đã được tẩy.

Điều đó **không** có nghĩa `Arrays.fill` vô dụng: nó là bước **best-effort** hợp lý để giảm thời gian tồn tại giá trị trong mảng do mình sở hữu. Khẳng định chính xác phải là “ứng dụng yêu cầu zero array cụ thể”, không phải “JVM/OS chứng minh toàn bộ secret đã bị tiêu huỷ”.

### 8.3. Biểu diễn dữ liệu và encoding

Java `char` là một **UTF-16 code unit**, không phải một byte UTF-8. Khi KDF hoặc giao thức cần password bytes, có thể phát sinh phép chuyển mã, bản sao của `byte[]`, chuẩn hóa Unicode và vùng nhớ của provider. Không coi `password.length` là số byte của password.

Để hai hệ thống dẫn xuất cùng khóa từ cùng mật khẩu, phải thống nhất **thuật toán KDF, salt, iterations/work factor, output length, encoding và normalization**; tránh tự chuyển đổi `char[]` sang String chỉ để “chuẩn hóa” mà không quản lý hậu quả. Các thuật toán PBE lịch sử có cách xử lý ký tự khác nhau; không tự suy diễn mọi provider đều chuyển char sang byte giống nhau.

### 8.4. Threat model quyết định mức cần thiết

Với một ứng dụng backend thông thường, ngăn mật khẩu trong logs, áp dụng KDF đúng, giới hạn quyền đọc heap dump và rút ngắn vòng đời bộ đệm có thể là những biện pháp thiết thực. Nhưng nếu đối thủ **đã chạy code trong cùng process hoặc có quyền đọc đầy đủ RAM**, việc zero một vài Java arrays không mang lại cách ly tuyệt đối.

Trong môi trường có yêu cầu rất cao, cân nhắc API/provider/HSM/KMS không xuất key material, tách tiến trình, giảm quyền tạo dump, mã hóa lưu trữ, hardening OS và thiết kế hạn chế nơi password dạng rõ được đưa tới. Java/JVM phổ thông không có contract tổng quát để “khóa trang nhớ và đảm bảo xóa mọi bản sao” chỉ bằng `char[]`.

## 9. Quy tắc triển khai thực tế: giảm lưu giữ bí mật có kiểm soát

### 9.1. Nguyên tắc ownership

- **Caller sở hữu** mảng do nó nhận từ UI/console/request: caller có trách nhiệm xóa sau khi xong, thường ở `finally`.
- **Callee chỉ giữ tạm** password khi xử lý và không lưu object/reference vào cache, field lâu dài, thread local, queue hoặc callback không cần thiết.
- Nếu thư viện tạo bản sao như `PBEKeySpec`, **đóng vòng đời bằng API chính thức** của thư viện (ở đây là `clearPassword`) thay vì tìm cách phản chiếu vào field private.
- Mảng `byte[]` từ encoding hay `getEncoded()` thuộc phạm vi caller khi đã nhận về: wipe khi không còn cần, nhưng hiểu rằng việc này **không** đụng tới material bên trong object khác.
- Không xóa buffer **trước khi** crypto API cần đọc nó. Sai thứ tự có thể khiến derive sai hoặc dẫn tới logic bảo mật sai. Tạo/derive xong, dọn buffer càng sớm càng tốt.

### 9.2. Vòng đời khuyến nghị

```text
NHẬN password vào char[] khi API đầu vào hỗ trợ
    |
    v
VALIDATE input tối thiểu (không log password)
    |
    v
Tạo PBEKeySpec (tạo bản sao nội bộ)
    |
    v
SecretKeyFactory / password verification / key derivation
    |
    +-- Dọn các byte[]/char[] tạm đã tạo và sở hữu
    +-- Dọn vật liệu khóa nếu API/provider có contract phù hợp
    |
    v
PBEKeySpec.clearPassword() trong finally
    |
    v
Arrays.fill(callerPassword, '\0') trong finally
    |
    v
Tiếp tục xử lý bằng kết quả xác minh/khóa được bảo vệ,
không giữ password dạng rõ lâu hơn cần thiết.
```

Không phải mọi hệ thống đều có đủ quyền kiểm soát để thực hiện toàn bộ quy trình; cần ghi rõ giới hạn của framework và thư viện.

### 9.3. Password hashing khác với quản lý password trong RAM

Việc chọn `char[]` và xoá bộ đệm **không thay thế** thuật toán password hashing chống dò offline. Nếu lưu thông tin xác thực người dùng, sử dụng password-hashing chuyên dụng có salt riêng cho mỗi tài khoản/bản ghi và chi phí đủ cao; ví dụ Argon2id hoặc lựa chọn phù hợp theo chính sách, thư viện và yêu cầu hệ thống. PBKDF2-HMAC-SHA256 có thể cần trong môi trường Java/JCA hay yêu cầu tương thích, nhưng cost factor phải được thiết kế/điều chỉnh, không lấy `10_000` trong demo làm khuyến nghị production.

Nếu dùng password để **mã hóa dữ liệu**, cần KDF phù hợp để dẫn xuất khóa và mode mã hóa được xác thực như AES-GCM với nonce đúng; không tự hash nhanh password bằng SHA-256 rồi dùng thẳng làm AES key nếu thiếu thiết kế và threat model. Salt, thông số KDF và IV thường **không bí mật**, nhưng cần lưu đúng để mở lại dữ liệu; **khóa dẫn xuất** và plaintext password phải được bảo vệ.

### 9.4. Log, telemetry và kiểm thử

- Không log password, salt+password, derived key bytes hay char[] bằng `toString()`/`Arrays.toString()`.
- Không đưa secret vào URL query, lỗi phản hồi, exception text, event bus hoặc environment variable nếu có lựa chọn an toàn hơn; môi trường và framework có thể giữ bản sao `String`.
- Khi test, dùng **giá trị giả**, không dùng tài khoản thật hoặc token production. Kiểm tra array đã zero được bằng logic test, nhưng **đừng** viết test khẳng định bộ nhớ native/heap dump hoàn toàn sạch.
- Kiểm tra `finally` trên cả đường thành công và thất bại: input invalid, exception từ KDF, timeout, cancellation, shutdown. Không để một exception làm bỏ qua bước cleanup của một buffer khác.
- Với xử lý bất đồng bộ, tránh giữ mật khẩu trong lambda/callback/`CompletableFuture`/queue lâu hơn mong muốn; tính lại ownership và thời điểm safe-to-clear.

## 10. Những ngộ nhận và lỗi thường gặp

| Ngộ nhận hoặc lỗi | Vì sao sai | Hướng khắc phục |
| --- | --- | --- |
| “Đã đổi `String` thành `char[]` nên password không thể bị lộ” | `char[]` vẫn ở heap, có thể bị copy, dump, log và bị đọc trong process | Quản lý vòng đời, quyền truy cập và threat model |
| “`clearPassword()` xoá mảng truyền vào constructor” | `PBEKeySpec` lưu bản sao nội bộ riêng | `clearPassword()` cho spec **và** `Arrays.fill` cho caller |
| “Gọi `getPassword()` nhiều lần không tốn bộ nhớ bí mật” | Mỗi lời gọi tạo một bản sao char[] mới | Tránh gọi thừa, wipe mọi bản sao đã nhận |
| “`Arrays.fill` xoá String được tạo trước đó” | String immutable/không cùng vùng nhớ | Tránh tạo String password ngay từ đầu khi có thể |
| “Đặt reference về `null` sẽ xoá password ngay” | GC không có hợp đồng wipe tức thời | Dọn buffer có thể sửa, giảm lifetime và bảo vệ dump |
| “`System.gc()` là API xóa secret” | Không có bảo đảm thời gian/ghi đè | Không dùng GC làm zeroization |
| “Đã xóa mảng `keyBytes` nên `SecretKey` chắc chắn bị xóa” | Object/provider có thể giữ key material riêng | Hạn chế export key và kiểm tra provider-specific cleanup |
| “Xoá password trước generateSecret sẽ an toàn hơn” | KDF cần dữ liệu đầu vào còn hợp lệ | Cleanup **sau** sử dụng, trong `finally` |
| “Password là char[] nên không thể xuất hiện trong log” | Logging, formatting hoặc debug có thể tạo String/ghi trực tiếp char[] | Thiết kế redaction và chính sách debug |
| “Xóa bộ nhớ thay thế được password hashing” | Dữ liệu mật khẩu bị rò rỉ từ DB vẫn có nguy cơ offline cracking | KDF/password-hashing có salt và cost phù hợp |
| “Một lần Arrays.fill chứng minh không còn password trong RAM” | Bản sao, provider, JIT/GC, native memory, swap, snapshots | Diễn đạt như **best-effort mitigation**, không cam kết tuyệt đối |

## 11. Bài tập và câu hỏi tự kiểm tra

1. `PBEKeySpec` được tạo từ `char[] original`. Nếu gọi `Arrays.fill(original, '\0')`, vì sao `SecretKeyFactory.generateSecret(spec)` vẫn có thể dẫn xuất khóa?
2. `spec.getPassword()` được gọi hai lần. Có bao nhiêu bản sao phải đánh giá về ownership? `spec.clearPassword()` có tự xóa cả hai mảng được trả về không?
3. Tại sao `new String(passwordChars)` là bước cần tránh trong luồng xử lý mật khẩu dù sau đó đã `Arrays.fill(passwordChars, '\0')`?
4. Nêu sự khác biệt giữa xóa mảng caller, xóa bản sao của spec, xóa `getEncoded()` result và phá hủy state của `SecretKey`/provider.
5. Vì sao `finally` quan trọng khi `SecretKeyFactory.generateSecret` có thể ném exception?
6. Nếu framework gửi password cho controller dưới dạng String, việc `toCharArray()` mang lại ích lợi gì và **không thể giải quyết** điều gì?
7. Vì sao “zero char[]” và “dùng Argon2id/PBKDF2 đúng chuẩn” giải quyết hai nhóm rủi ro khác nhau?
8. Những thông tin nào có thể còn tồn tại trong heap dump hoặc snapshot dù tất cả mảng Java bạn thấy đều đã fill NUL?

**Thực hành:** sửa demo để gọi `spec.getPassword()` lần thứ hai rồi kiểm tra hai bản copy không cùng reference và phải được wipe độc lập. Thêm nhánh giả lập exception trong `try`, bảo đảm `finally` chạy và không in mật khẩu. Viết test cho `spec.getPassword()` sau `clearPassword()` ném `IllegalStateException`. Không chạy các thí nghiệm với mật khẩu thật, không ghi heap dump chứa secret production.

## 12. Tài liệu API chính thức

- [PBEKeySpec — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): constructor, `getPassword`, `clearPassword`, sao chép password/salt và ngoại lệ sau clear.
- [SecretKeyFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html): tạo khóa bí mật từ `KeySpec` qua provider.
- [Arrays — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `Arrays.fill(char[], char)` và `Arrays.fill(byte[], byte)`.
- [Console — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html): `readPassword` và hành vi khi không có interactive console.
- [JPasswordField — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/swing/JPasswordField.html): `getPassword()` thay cho các cách xử lý String không cần thiết.
- [Java Cryptography Architecture (JCA) Reference Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): khái niệm key, provider, `SecretKeyFactory` và password-based derivation.
