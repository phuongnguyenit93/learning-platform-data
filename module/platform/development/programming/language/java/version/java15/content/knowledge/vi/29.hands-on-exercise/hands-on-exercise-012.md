# Bài tổng hợp trên JDK được hỗ trợ với các năng lực Java 15 còn áp dụng

## 1. Đề bài thực hành và phạm vi phiên bản

Bạn được giao xây dựng một tiện ích Java nhận nội dung sự kiện triển khai, chuẩn hóa văn bản, tạo báo cáo nhiều dòng, chuyển báo cáo qua một bộ định dạng được nạp động, sau đó **ký số bằng Ed25519**. Bộ kiểm thử phải chứng minh báo cáo có nội dung chính xác, hidden class được định nghĩa đúng cơ chế, chữ ký hợp lệ và mọi thay đổi sau khi ký đều bị phát hiện.

Bài tập sử dụng các tính năng **trở thành chính thức trong Java 15 và vẫn được hỗ trợ**:

| Năng lực | Nền tảng | Vai trò trong bài |
| --- | --- | --- |
| **Text blocks** — JEP 378 | Ngôn ngữ Java, chính thức từ JDK 15 | Viết mẫu báo cáo nhiều dòng, dễ đọc, không cần ghép nhiều literal |
| `String.formatted()` | `java.lang.String`, từ Java 15 | Thay các tham số `%s` trong text block bằng dữ liệu |
| `String.stripIndent()` | `java.lang.String`, từ Java 15 | Chuẩn hóa lề một đoạn văn bản runtime |
| `String.translateEscapes()` | `java.lang.String`, từ Java 15 | Diễn giải escape sequence hợp lệ trong chuỗi runtime |
| **Hidden classes** — JEP 371 | `MethodHandles.Lookup.defineHiddenClass`, từ Java 15 | Định nghĩa lớp trợ giúp bằng bytecode cùng package của lookup, gọi qua `MethodHandle` |
| **EdDSA / Ed25519** — JEP 339 | Java Cryptography Architecture, từ Java 15 | Ký và xác minh **đúng bytes** của báo cáo |
| `record` | Chính thức từ Java 16 | Dùng kiểu trả về gọn, bất biến cho kết quả hidden class; là cú pháp hiện hành trên JDK 17+ |

**Yêu cầu JDK:** Dùng **JDK 17 trở lên** để biên dịch/chạy mã trong bài; chương trình biên dịch bằng `javac --release 17` và không cần bật `--enable-preview`. Java 15 là mốc lịch sử ra mắt các API chính được luyện tập, không phải phiên bản runtime cần cố định ở sản phẩm hiện nay. `record` được dùng vì đã là tính năng ổn định trên JDK mục tiêu của bài.

Một số hướng đi từng xuất hiện dưới dạng *preview* ở Java 15 sau đó đã trở thành tính năng chính thức trong những bản JDK mới hơn, ví dụ records (Java 16), pattern matching cho `instanceof` (Java 16) và sealed classes (Java 17). Khi viết ứng dụng mới trên JDK 17+, hãy sử dụng cú pháp chính thức theo target JDK; bài này không phụ thuộc bản preview, API incubator hay hành vi đã bị loại bỏ.

### Tiêu chí hoàn thành

- Dùng text block cùng `formatted()` để tạo một báo cáo có nội dung và thứ tự dòng được kiểm thử chính xác.
- Nhận dữ liệu chứa escape `\n` ở dạng **hai ký tự** trong `String`, dịch thành LF thực khi cần; xử lý lỗi escape sai.
- Dùng `stripIndent()` để bỏ lề chung nhưng vẫn giữ thụt lề tương đối.
- Nạp bytecode trợ giúp từ tài nguyên `.class`, tạo **hidden class** bằng một lookup có đầy đủ đặc quyền ở đúng package, gọi phương thức bằng `MethodHandle`.
- Ký báo cáo bằng cặp khóa Ed25519 vừa sinh; xác minh bằng public key; thay đổi payload hoặc đổi public key phải cho kết quả `false`.
- Chạy từ thư mục chứa các class được biên dịch **và** từ JAR thật. Cả hai cách đều phải in ra `PASS 11 checks`.

## 2. Thiết kế luồng xử lý

```text
Input text được kiểm soát trong ví dụ
       |
       +-- "    alpha\n      beta"  -- stripIndent() --> "alpha\n  beta"
       |
       +-- "ready\\nnext"          -- translateEscapes() --> "ready\nnext"
       |
       v
Text block cố định + formatted(...)  --> báo cáo dạng String
       |
       v
CapstoneDemo đọc HiddenRenderer.class
       |
       v
Lookup.defineHiddenClass(...) --> MethodHandle gọi render(String)
       |
       v
Báo cáo đã bọc BEGIN/END, encode UTF-8
       |
       +--> Ed25519 ký bằng PrivateKey
       |
       +--> Ed25519 verify bằng PublicKey: true
       |
       +--> Thêm "!" sau khi ký rồi verify: false
       |
       +--> Verify với public key khác: false
```

Trong ví dụ, chuỗi đầu vào được viết ngay trong mã để test có thể tái lập. Khi áp dụng cho HTTP/file/database, **validate dữ liệu tại ranh giới đầu vào**: kiểu, độ dài, giá trị cho phép, encoding, giới hạn số dòng và quyền truy cập. `stripIndent()` không tự xác minh schema; `translateEscapes()` không phải trình parser JSON.

**Đối tượng cần ký:** ký bytes của **bản báo cáo cuối cùng sau tất cả bước format**, không ký dữ liệu ban đầu rồi tiếp tục biến đổi. Nếu hai bên ký/xác minh dùng các bytes khác nhau dù chỉ khác LF/CRLF hoặc một space, việc verify sẽ thất bại. Ở đây dùng `StandardCharsets.UTF_8` và cố định trình tự tạo báo cáo.

## 3. Chuẩn bị dự án Java chỉ dùng JDK

Không cần Maven, Gradle, JSON library hay database. Chỉ cần `java`, `javac` và `jar` từ JDK 17+.

Cấu trúc thư mục:

```text
java15-capstone/
├── src/
│   └── lab/
│       ├── CapstoneDemo.java
│       └── HiddenRenderer.java
└── out/                   # được tạo bởi javac sau khi biên dịch
```

Hai file Java **cùng package `lab`**. Điều này rất quan trọng: bytecode đưa vào `Lookup.defineHiddenClass` phải có tên lớp nằm trong cùng package với lookup class; phương thức trợ giúp có thể được gọi thông qua lookup do API trả về. Khi đóng JAR, phải giữ cả `CapstoneDemo.class` và `HiddenRenderer.class`.

### 3.1. Bộ định dạng đầu vào: `src/lab/HiddenRenderer.java`

```java
package lab;

final class HiddenRenderer {
    static String render(String text) {
        return "BEGIN\n" + text + "END\n";
    }
}
```

Đây là class thường được `javac` biên dịch để tạo bytecode mẫu `HiddenRenderer.class`. Khi đọc lại bytecode đó và gọi `defineHiddenClass`, JVM định nghĩa **một lớp khác** mang định danh hidden riêng. Việc có file `HiddenRenderer.class` thông thường trong JAR **không làm cho chính file class đã nạp thông thường trở thành hidden class**. Trong framework sản xuất, bytecode có thể được sinh động thay vì lấy từ class đã biên dịch sẵn; ví dụ này tập trung vào API và ranh giới quyền truy cập.

Lớp trợ giúp cố ý không có `public`, và phương thức `render` là package-private. Chương trình chính sẽ không gọi trực tiếp `new HiddenRenderer()`; nó gọi phương thức của hidden class qua `MethodHandle`.

### 3.2. Chương trình chính và bộ kiểm thử: `src/lab/CapstoneDemo.java`

```java
package lab;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public final class CapstoneDemo {
    private static int passed = 0;

    private static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
        passed++;
    }

    private record HiddenResult(Class<?> type, String text) {}

    private static HiddenResult renderByHiddenClass(String content) throws Throwable {
        byte[] classBytes;
        try (InputStream in = CapstoneDemo.class.getResourceAsStream(
                "HiddenRenderer.class")) {
            if (in == null) {
                throw new IOException("HiddenRenderer.class was not packaged");
            }
            classBytes = in.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(classBytes, true);
        Class<?> hiddenType = hiddenLookup.lookupClass();

        MethodHandle render = hiddenLookup.findStatic(
                hiddenType, "render", MethodType.methodType(String.class, String.class));
        return new HiddenResult(hiddenType, (String) render.invokeExact(content));
    }

    private static byte[] sign(PrivateKey key, byte[] payload) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(key);
        signer.update(payload);
        return signer.sign();
    }

    private static boolean verify(PublicKey key, byte[] payload, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(payload);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Throwable {
        String clean = "    alpha\n      beta".stripIndent();
        check(clean.equals("alpha\n  beta"), "stripIndent");

        String decoded = "ready\\nnext".translateEscapes();
        check(decoded.equals("ready\nnext"), "translateEscapes");

        String payload = """
                event=%s
                detail=%s
                status=%s
                """.formatted(
                "release",
                clean.replace("\n", " / "),
                decoded.replace("\n", " / "));

        String expectedPayload =
                "event=release\ndetail=alpha /   beta\nstatus=ready / next\n";
        check(payload.equals(expectedPayload), "text block + formatted");

        HiddenResult hidden = renderByHiddenClass(payload);
        check(hidden.type().isHidden(), "hidden class was created");
        check(hidden.text().equals("BEGIN\n" + expectedPayload + "END\n"),
                "hidden class rendered correct content");

        boolean loadByNameFailed = false;
        try {
            Class.forName(hidden.type().getName());
        } catch (ClassNotFoundException expected) {
            loadByNameFailed = true;
        }
        check(loadByNameFailed, "hidden class cannot be loaded by binary name");

        KeyPair pair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        byte[] bytes = hidden.text().getBytes(StandardCharsets.UTF_8);
        byte[] signature = sign(pair.getPrivate(), bytes);

        check(signature.length == 64, "Ed25519 signature length");
        check(verify(pair.getPublic(), bytes, signature), "valid Ed25519 signature");
        check(!verify(pair.getPublic(),
                (hidden.text() + "!").getBytes(StandardCharsets.UTF_8), signature),
                "tampered message rejected");

        KeyPair unrelated = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        check(!verify(unrelated.getPublic(), bytes, signature),
                "unrelated public key rejected");

        boolean invalidEscapeRejected = false;
        try {
            "\\q".translateEscapes();
        } catch (IllegalArgumentException expected) {
            invalidEscapeRejected = true;
        }
        check(invalidEscapeRejected, "malformed escape rejected");

        System.out.println("PASS " + passed + " checks");
    }
}
```

**Vì sao `main` khai báo `throws Throwable`?** `MethodHandle.invokeExact` được thiết kế có thể ném `Throwable`. Cách viết này thuận tiện cho bài thực hành độc lập; trong ứng dụng sản xuất, hãy xử lý/ánh xạ lỗi tại biên giới của component phù hợp.

**Vì sao dùng `record HiddenResult`?** Để đóng gói hai giá trị `Class<?>` và chuỗi kết quả thành một đối tượng bất biến, giảm việc dùng mutable holder. Đây là cú pháp chính thức từ Java 16, nên toàn bộ mẫu biên dịch với `--release 17`; không cần tính năng preview của Java 15.

## 4. Biên dịch, chạy từ class directory và từ JAR

Từ thư mục gốc `java15-capstone`, chạy:

```bash
javac --release 17 -d out src/lab/CapstoneDemo.java src/lab/HiddenRenderer.java
java -cp out lab.CapstoneDemo
```

Stdout **chính xác**:

```text
PASS 11 checks
```

Tiếp tục đóng JAR cùng hai class và chạy từ JAR:

```bash
jar --create --file capstone.jar -C out .
java -cp capstone.jar lab.CapstoneDemo
```

Stdout cũng là:

```text
PASS 11 checks
```

Lệnh `jar` dùng classpath JAR bình thường, không yêu cầu `module-info.java`. Đây là lựa chọn có chủ đích để học API độc lập với cấu hình module. Nếu đưa vào **named module** thực tế, `Lookup.defineHiddenClass` vẫn yêu cầu full-privilege lookup trong đúng runtime package/module; ngoài ra cần thiết kế `requires`/`exports`/`opens` khi qua ranh giới module.

Mẫu trên đã được kiểm chứng trên **JDK 24**, biên dịch bằng `--release 17`, sau đó chạy cả từ thư mục class lẫn JAR. `--release 17` giới hạn cú pháp và API theo Java 17 khi biên dịch; tuy vậy, chạy thật trên phiên bản JDK thấp nhất được dự án hỗ trợ vẫn là bước bắt buộc trong CI nếu bạn cam kết tương thích đa runtime.

### Tự quan sát nội dung JAR

```bash
jar --list --file capstone.jar
```

Danh sách phải có ít nhất `lab/CapstoneDemo.class`, `lab/CapstoneDemo$HiddenResult.class` và `lab/HiddenRenderer.class`, cùng metadata JAR. Nếu quá trình đóng gói, shading hoặc minimization loại `HiddenRenderer.class`, chương trình sẽ báo `IOException` với thông điệp `HiddenRenderer.class was not packaged`. Không nên xử lý bằng cách lấy bytecode từ thư mục source ở runtime.

## 5. Phân tích 11 kiểm tra

| Kiểm tra | Kỳ vọng | Kiến thức được xác nhận |
| --- | --- | --- |
| 1. `stripIndent()` | `"alpha\n  beta"` | Bỏ chung bốn dấu cách đầu dòng, giữ lại hai dấu cách tương đối |
| 2. `translateEscapes()` | `"ready\nnext"` | Dữ liệu `\\n` gồm dấu backslash + chữ n được chuyển thành LF thực |
| 3. Text block và `formatted()` | Chuỗi 3 dòng kết thúc bằng LF | Text block tự xử lý lề compiler; `%s` nhận đúng tham số |
| 4. Hidden class | `hidden.type().isHidden() == true` | Bytecode đã được định nghĩa như hidden class mới |
| 5. Nội dung do hidden class render | `"BEGIN\n" + payload + "END\n"` | `MethodHandle` gọi đúng phương thức và tham số |
| 6. Không nạp hidden class theo binary name | `ClassNotFoundException` khi `Class.forName(hiddenName)` | Hidden class không là class thông thường có thể tìm lại theo tên |
| 7. Kích thước chữ ký | 64 bytes | Ed25519 tạo chữ ký có kích thước xác định |
| 8. Kiểm tra chữ ký nguyên bản | `true` | Public key của cặp đã ký xác minh đúng bytes |
| 9. Sửa payload sau ký | `false` | Kiểm tra toàn vẹn thông điệp |
| 10. Đổi sang public key khác | `false` | Chữ ký không được xác minh bởi khóa không tương ứng |
| 11. Escape sai `\\q` | `IllegalArgumentException` | `translateEscapes()` phát hiện grammar không hợp lệ |

Chương trình dùng phương thức `check` tự tạo, nên các kiểm tra thực hiện dù không bật Java assertions. Khi một kiểm tra sai, nó ném `AssertionError` và tiến trình kết thúc khác thành công; chỉ khi toàn bộ mười một kiểm tra qua mới in dòng `PASS 11 checks`. Các khóa sinh ngẫu nhiên mỗi lần chạy nhưng stdout vẫn xác định vì chỉ in **kết quả boolean**, không in bytes của khóa hoặc chữ ký.

### 5.1. Text blocks, whitespace và input khác nhau

Text block là **literal được compiler xử lý**. Khi dùng:

```java
String fixed = """
        event=%s
        detail=%s
        status=%s
        """;
```

String `fixed` chứa ba dòng và một LF cuối. Lề phục vụ bố cục source đã được compiler loại bỏ. `formatted` là một cách gọi `String.format(this, args)`, nên nếu input chứa `%` được truyền như **argument** cho `%s`, nội dung đó không được đọc lại như format string mới.

`stripIndent` lại xử lý một **String runtime**. Trong ví dụ `"    alpha\n      beta"` không có LF ở cuối, nên lề chung được bỏ và hai dấu cách dư trước `beta` được giữ. Nếu thay input bằng `"    alpha\n      beta\n"` thì **dòng cuối rỗng** ảnh hưởng đến min-indent; không được suy luận rằng kết quả sẽ giống trường hợp không có LF cuối.

`translateEscapes` chỉ diễn giải những escape mà Java String API hỗ trợ; `"ready\\nnext"` trong source đại diện cho một `String` thực có dấu `\` rồi chữ `n`, không phải LF từ đầu. `"\\q"` là một escape *trong dữ liệu runtime* không hợp lệ và bị từ chối. API này không phải JSON decoder và không diễn giải `\uXXXX` ở runtime như JSON parser; nếu nguồn là JSON phải dùng thư viện JSON phù hợp.

### 5.2. Hidden classes và ranh giới `Lookup`

Đây là phần dễ dùng sai khi chuyển từ ví dụ sang thư viện hoặc framework:

- `MethodHandles.lookup()` có ngữ cảnh của class đang **gọi** phương thức đó. Trong `CapstoneDemo`, lookup thuộc `lab.CapstoneDemo`, cùng package với class mẫu `lab.HiddenRenderer`.
- `defineHiddenClass(classBytes, true)` đòi hỏi lookup có **full privilege access**, bytecode hợp lệ và tên package phù hợp. `true` yêu cầu khởi tạo hidden class khi định nghĩa.
- API trả một `Lookup` mới; `lookupClass()` chỉ tới hidden class. Có thể dùng lookup này để tìm `render(String)`, sau đó gọi qua `MethodHandle.invokeExact`.
- Hidden class có danh tính `Class<?>` riêng và có thể kiểm tra bằng `isHidden()`, nhưng **không thể tìm lại qua `Class.forName` bằng tên do `getName()` trả về**.
- Hidden classes phục vụ các trường hợp code generation/framework. Chúng **không tự động trở thành sandbox bảo mật** và không thay thế xác minh bytecode đầu vào. Mẫu dùng bytecode **được build cùng ứng dụng**; tránh truyền bytes từ nguồn không tin cậy vào một lookup đặc quyền.
- Với named modules, `opens` một package cho module khác có thể cho phép private lookup qua điều kiện phù hợp, nhưng lookup được trả sau thao tác **cross-module `privateLookupIn`** không giữ mode `MODULE` và không đủ để `defineHiddenClass`. Đặt factory tạo hidden class vào module/package sở hữu bytecode.

Nếu chỉ cần định dạng chuỗi cố định trong ứng dụng nghiệp vụ, gọi một method hoặc lambda bình thường sẽ đơn giản hơn. Hidden class là bài thực hành về năng lực của runtime và boundary; chỉ dùng trong sản phẩm khi có lý do rõ như tạo implementation động, runtime framework, hoặc hệ thống sinh mã.

### 5.3. Ed25519 ký dữ liệu sau xử lý

`KeyPairGenerator.getInstance("Ed25519")` tạo cặp khóa. `Signature.getInstance("Ed25519")` thực thi hai vai trò khác nhau tùy được khởi tạo với private/public key.

**Ký:**

```java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(payloadUtf8);
byte[] signature = signer.sign();
```

**Xác minh:**

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);
verifier.update(payloadUtf8);
boolean valid = verifier.verify(signature);
```

Đây là **hai đoạn code minh họa**, dùng các biến đã được khai báo trong ngữ cảnh; chương trình đầy đủ nằm ở mục 3. Chữ ký giúp xác minh rằng thông điệp không bị thay đổi và được tạo bằng private key tương ứng với public key tin cậy. Nó **không mã hóa nội dung** và không che giấu báo cáo.

Trong ứng dụng thật:

- Không sinh cặp khóa tạm **cho mỗi lần cần xác minh lâu dài** như demo. Quản lý vòng đời khóa, phát hành public key qua kênh tin cậy, lưu private key an toàn (keystore/KMS/HSM theo môi trường) và xác định kế hoạch quay vòng/thu hồi.
- Thiết kế **canonical representation** của thông điệp trước khi ký: UTF-8, line endings, thứ tự field, timezone, JSON canonicalization nếu có. Cùng dữ liệu logic nhưng bytes khác sẽ không xác minh được.
- Không ghi private key vào log, fixture, CI artifact hoặc repository; không gửi nó cùng báo cáo đã ký.
- Với giao thức có nhiều loại thông điệp, đưa domain/version/loại payload vào cấu trúc đã ký để tránh tái sử dụng chữ ký ngoài ngữ cảnh dự kiến.
- Chỉ dùng provider/thuật toán được môi trường triển khai hỗ trợ và chính sách bảo mật chấp thuận; không tự triển khai thuật toán mật mã.

## 6. Kiểm thử dữ liệu biên và đường thất bại

Bộ 11 kiểm tra là tiêu chí tối thiểu cho luồng chính. Khi dùng bài này làm nền tảng cho mã production, bổ sung các nhóm sau.

| Nhóm | Đầu vào hoặc thao tác | Kỳ vọng/test cần bổ sung |
| --- | --- | --- |
| Văn bản rỗng | `""`, toàn space, LF đầu/cuối | Quy tắc lề và dòng cuối phải rõ; validator từ chối nếu nghiệp vụ yêu cầu nội dung |
| CR/LF | `\r`, `\n`, `\r\n` trộn nhau | Kiểm tra LF sau `stripIndent` và bytes UTF-8 cuối cùng trước khi ký |
| Tab | Dòng bắt đầu bằng `\t` | Mỗi tab là một ký tự whitespace, không tự mở thành 4/8 space |
| Unicode | Ký tự tiếng Việt, emoji, NBSP | So sánh chính xác giá trị; xác định cách đếm độ dài và chuẩn Unicode |
| Escape hợp lệ | `\\t`, `\\s`, `\\\\`, octal | Xác nhận output theo grammar của `translateEscapes` |
| Escape sai | `\\q`, dấu `\` ở cuối, `\\8` | `IllegalArgumentException`; lỗi được biến thành phản hồi có kiểm soát |
| Thiếu resource | Loại `HiddenRenderer.class` khỏi JAR | `IOException` có thông điệp rõ; kiểm tra quy trình đóng gói |
| Bytecode khác package | Cung cấp class bytes của package khác lookup | Định nghĩa bị từ chối; không dùng lookup để vượt ranh giới package |
| Lookup thiếu quyền | Dùng `MethodHandles.publicLookup()` để định nghĩa hidden class | `IllegalAccessException` hoặc lỗi quyền thích hợp |
| Dữ liệu sau ký bị thay đổi | Đổi ký tự, thêm LF hoặc space | Verify trả `false` |
| Sai public key | Key của người không tương ứng | Verify trả `false` |
| Bytecode/algorithm không được hỗ trợ | Runtime hoặc provider thiếu năng lực | Báo lỗi cấu hình rõ, không tự fallback sang thuật toán không chấp thuận |

**Lưu ý về chữ ký:** thay đổi một ký tự Unicode có thể làm thay đổi nhiều byte UTF-8; verify so sánh chữ ký với bytes thực, không với “văn bản nhìn gần giống nhau”. Khi cần ký dữ liệu trao đổi giữa hệ thống, thống nhất canonicalization và xác minh byte-for-byte.

**Lưu ý về negative test:** hãy so sánh đúng **loại lỗi** và hợp đồng, tránh gắn chặt với toàn bộ thông điệp ngoại lệ nội bộ của JVM vì câu chữ có thể khác giữa các bản JDK. Một thao tác sai được xử lý là “test PASS” chỉ khi lỗi là điều **được mong đợi và đã kiểm chứng**.

### 6.1. Áp dụng JUnit Jupiter khi đưa vào dự án thật

Chương trình `CapstoneDemo` dùng `check` để tự chạy không phụ thuộc framework. Trong dự án có JUnit Jupiter, chia các case thành các test độc lập dùng `@Test` và `assertEquals`/`assertTrue`/`assertFalse`/`assertThrows`. Ví dụ sau là **test fragment yêu cầu JUnit Jupiter và code ứng dụng phù hợp**, không phải một chương trình `javac` độc lập:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class StringContractsTest {
    @Test
    void stripsCommonIndent() {
        assertEquals("alpha\n  beta",
                "    alpha\n      beta".stripIndent());
    }

    @Test
    void rejectsMalformedEscape() {
        assertThrows(IllegalArgumentException.class,
                () -> "\\q".translateEscapes());
    }

    @Test
    void translatesRuntimeNewlineEscape() {
        assertEquals("ready\nnext",
                "ready\\nnext".translateEscapes());
    }
}
```

Với phần chữ ký, có thể thêm test verify với public key khác, payload bị thêm ký tự, và byte array bị đổi một vị trí. Với phần hidden class, kiểm tra `isHidden()` và output của `MethodHandle` trong test tích hợp có chứa resource bytecode thực. Tách unit test string khỏi integration test package, vì lỗi resource bị loại khi đóng JAR có thể không xuất hiện khi test trực tiếp từ thư mục class.

## 7. Kiểm tra khi nâng cấp JDK và phát hành sản phẩm

Mục tiêu của bài không dừng ở “chạy được trên JDK cài trong IDE”. Hãy kiểm tra môi trường build, runtime và artifact.

### 7.1. Phân biệt JDK biên dịch và JDK chạy

- `java -version` cho biết JVM đang chạy; `javac -version` cho biết compiler. Kiểm tra cả hai trước khi kết luận lỗi do source.
- `javac --release 17` kiểm soát mức API và bytecode tương thích Java 17; **không chứng minh** chương trình đã được chạy kiểm thử trên mọi JDK 17+.
- Nếu dự án yêu cầu JDK 21 hoặc 25 để chạy, chọn `--release` phù hợp với cam kết tương thích và biên dịch/test trên các bản JDK mục tiêu. Không dùng API chỉ có trên bản JDK mới hơn mức `--release` đã chọn.
- Chạy ít nhất bộ kiểm thử trên **JDK tối thiểu được hỗ trợ** và JDK triển khai. Đặc biệt với code động, Reflection, crypto provider, module path và packaging, lỗi có thể chỉ lộ ra ở môi trường runtime.

### 7.2. Đóng gói class và resource

`CapstoneDemo.class.getResourceAsStream("HiddenRenderer.class")` tìm resource cùng package `lab`. Khi build ra JAR, class trợ giúp phải tồn tại trong `lab/`. Với plugin minimization/shading, có thể bị loại khi công cụ không thấy call trực tiếp tới `HiddenRenderer`. Hãy cấu hình packaging để giữ resource này và test **JAR cuối cùng** như ở mục 4.

Các thao tác kiểm tra thực tế:

```bash
jar --list --file capstone.jar
java -cp capstone.jar lab.CapstoneDemo
```

Trong ứng dụng named-module, còn phải kiểm tra `module-info.class`, đường dẫn module, quyền đọc module và package. Không mở mọi package bằng `--add-opens` để che lỗi thiết kế lâu dài; cân nhắc đặt factory vào module chủ sở hữu package.

### 7.3. Vị trí của Garbage Collectors Java 15 trong hệ thống hiện hành

Ngoài những API trong ví dụ, Java 15 còn đánh dấu **ZGC** (JEP 377) và **Shenandoah** (JEP 379) ở trạng thái sẵn sàng sử dụng trong production. Chúng là những lựa chọn GC vẫn liên quan khi tối ưu latency, nhưng **không cần đổi GC** để chạy chương trình capstone này. Trên JDK hiện đại, việc có hỗ trợ một collector cụ thể có thể phụ thuộc bản phát hành/vendor, hệ điều hành, cấu hình và thay đổi của bản JDK; cần đối chiếu tài liệu runtime và đo thực tế bằng workload, metrics, GC logs trước khi chọn. Không suy luận rằng GC hiệu quả hơn với mọi ứng dụng chỉ vì nó nhắm đến low latency.

Trong bài này, bộ kiểm thử không dựa vào collector, thread scheduling, locale, clock hay random key bytes cụ thể. Nhờ đó `PASS 11 checks` là kết quả xác định dù một cặp khóa Ed25519 mới được sinh ra ở mỗi lần chạy.

## 8. Lỗi thường gặp khi làm bài tổng hợp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chép text block rồi gọi thêm `stripIndent` mà không kiểm tra LF cuối | Dời lề khác kỳ vọng hoặc vô tình thay đổi thông điệp trước khi ký | So sánh exact string và bytes trước bước ký |
| Nhầm `"ready\\nnext"` với `"ready\nnext"` | Test thực tế đang dùng đầu vào khác dự định | Viết test so sánh LF thực và escape raw riêng |
| Xem `translateEscapes` như bộ parser JSON | `\\uXXXX` hoặc grammar JSON không xử lý như mong muốn | Dùng JSON parser cho JSON; chỉ gọi API theo hợp đồng dữ liệu |
| Tạo lookup bằng `publicLookup()` hoặc di chuyển factory qua module khác | Không đủ quyền định nghĩa hidden class | Tạo full-privilege lookup trong module/package sở hữu bytecode |
| Chỉ giữ `CapstoneDemo.class` trong JAR | Không tìm được `HiddenRenderer.class` tại runtime | Test artifact JAR thật và giữ resource trợ giúp |
| Coi hidden class là lớp có thể gọi theo tên `Class.forName` | Không tìm thấy tên hidden class | Giữ tham chiếu `Class<?>`/`MethodHandle` do API trả về |
| Đưa bytecode từ đầu vào không tin cậy vào lookup đặc quyền | Mở đường cho logic không được kiểm soát chạy trong package/module | Chỉ dùng bytecode đã xác minh và giữ factory trong vùng tin cậy |
| Ký văn bản trước rồi thay đổi newline/space hoặc encoding | Chữ ký không khớp với bản cuối | Chuẩn hóa trước, ký bytes cuối, giữ representation nhất quán |
| Coi Ed25519 là mã hóa nội dung | Báo cáo vẫn đọc được bởi người nhận bytes | Dùng encryption riêng nếu cần bí mật; chữ ký phục vụ xác thực/toàn vẹn |
| Chỉ test chữ ký hợp lệ | Không chứng minh việc phát hiện sửa đổi | Thêm negative test đổi payload và public key |
| Lưu private key trong source hoặc log | Tăng nguy cơ lộ khóa | Dùng keystore/KMS và quản lý quyền/chính sách vòng đời |
| Dùng `--enable-preview` không cần thiết trên JDK 17+ | Phát sinh phụ thuộc không có ích và sai định hướng ổn định | Biên dịch với `--release` và API đã chính thức |
| Chỉ chạy file `.class` khi phát triển | Bỏ sót lỗi đóng gói resource của hidden class | Chạy từ JAR thực tế trên runtime mục tiêu |

## 9. Bài tập mở rộng để tự đánh giá

Các bài tập này phát triển trực tiếp từ chương trình đã chạy:

1. **Thêm dữ liệu thực tế:** Cho phương thức tạo báo cáo nhận `event` và `detail` từ tham số, kiểm tra `null`, chuỗi rỗng và độ dài tối đa trước khi format. Giữ template text block cố định và không cho input trở thành format string.
2. **Thêm ma trận whitespace:** Kiểm thử CRLF, tab, dòng trắng cuối, dấu cách cuối dòng, ký tự tiếng Việt và NBSP. Ghi `expected` bằng mã Java cố định để nhìn được chính xác LF và space.
3. **Thay một byte:** Sau khi ký, clone `byte[]` và đổi một vị trí, xác minh chữ ký thất bại; xác minh lại bytes nguyên bản phải đúng. Không cần log signature hoặc private key.
4. **Kiểm tra jar thiếu helper:** Tạo một artifact test không chứa `lab/HiddenRenderer.class`, chạy và kiểm tra ngoại lệ thiếu resource. Sau đó trở lại artifact chuẩn và xác minh đủ 11 checks.
5. **Áp dụng named module:** Chuyển mã sang một module sở hữu cả hai class, chạy trên `--module-path`, dùng lookup được tạo trong module đó. Phân biệt rõ việc export API `public` cho client và đặc quyền nội bộ cần để tạo hidden class.
6. **Bổ sung test theo JDK mục tiêu:** Chạy cùng mã nguồn trên bản JDK thấp nhất dự án cam kết và bản dùng khi triển khai. Ghi nhận version, lệnh build, stdout, lỗi môi trường và kết quả chạy JAR.
7. **Thiết kế key management:** Thay khóa tạo tạm bằng cặp khóa lưu/quản lý an toàn theo chính sách tổ chức; public key phải được phân phối đáng tin cậy. Kiểm tra cơ chế xác định key ID/version và chống nhầm ngữ cảnh chữ ký.

Gợi ý tiêu chí tự chấm: chương trình cần bảo toàn đúng văn bản và UTF-8 bytes; định nghĩa hidden class thành công với lookup hợp lệ; chữ ký nguyên vẹn được xác minh; chữ ký cho dữ liệu đã sửa và public key sai bị từ chối; artifact JAR chạy độc lập; không cần preview feature hoặc thư viện ngoài; báo lỗi rõ ở các nhánh thất bại.

## 10. Tham khảo chính thức

- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text blocks chính thức từ Java 15 và quy tắc whitespace.
- [Javadoc `String`, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `formatted()`, `stripIndent()`, `translateEscapes()` và exception contracts.
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): mục đích và đặc tính của hidden classes.
- [Javadoc `MethodHandles.Lookup`, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, quyền lookup và giới hạn theo module.
- [JEP 339 — Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): EdDSA/Ed25519 được đưa vào JDK 15.
- [Javadoc `Signature`, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): quy trình `initSign`/`update`/`sign` và `initVerify`/`verify`.
- [JEP 377 — ZGC (Production)](https://openjdk.org/jeps/377), [JEP 379 — Shenandoah (Production)](https://openjdk.org/jeps/379): các thay đổi GC của Java 15 vẫn có ý nghĩa khi chọn runtime trên JDK hiện đại.
- [Java Compiler — `javac`, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): tùy chọn `--release` và khả năng tương thích biên dịch.
