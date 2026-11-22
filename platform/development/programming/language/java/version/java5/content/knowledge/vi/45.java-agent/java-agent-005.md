# ClassFileTransformer và đường đi biến đổi lớp lúc nạp

`ClassFileTransformer` là điểm nối giữa Java agent và dữ liệu lớp mà JVM sắp định nghĩa. Thay vì sửa mã nguồn rồi biên dịch lại ứng dụng, agent có thể cung cấp một dãy byte lớp khác ngay trên đường nạp.

Điều cần nắm đầu tiên: **byte của lớp đi qua hàm `transform`; lời gọi phương thức của ứng dụng không đi qua hàm này mỗi lần chạy**. Nếu muốn đo thời gian từng lần gọi, công cụ phải chèn mã đo vào bytecode mà phương thức sẽ thực thi.

## 1. Nhìn đường đi trước khi đọc API

Với một lớp ứng dụng được nạp lần đầu, có thể hình dung:

```text
Nguồn lớp mà ClassLoader tìm thấy
              |
              v
      byte lớp ban đầu B0
              |
              v
     chuỗi ClassFileTransformer
              |
              v
      byte lớp cuối cùng Bn
              |
              v
   JVM kiểm tra và định nghĩa lớp
              |
              v
  liên kết, khởi tạo khi được yêu cầu
              |
              v
     thực thi phương thức ứng dụng
```

Sơ đồ tập trung vào phần biến đổi trong quá trình định nghĩa lớp; không có nghĩa mọi lớp chỉ được nạp khi chương trình gọi phương thức đầu tiên.

Agent đăng ký transformer bằng `Instrumentation.addTransformer(...)`. Đăng ký không tự chạy lại quá trình nạp của các lớp đã có. Cơ chế yêu cầu biến đổi lại lớp đã nạp là một thao tác riêng; bài này chỉ thực hành lần định nghĩa đầu tiên. Xem [Instrumentation.addTransformer](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#addTransformer(java.lang.instrument.ClassFileTransformer)).

Trong bài thực hành, kết quả cuối cùng sẽ đổi từ `ORIGINAL` sang `AGENT`, trong khi tệp `Target.class` của ứng dụng trên đĩa vẫn giữ nguyên.

## 2. Hợp đồng của transform

Mã Java 17+ có thể ghi đè dạng nhận thông tin module:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    // Lọc lớp và tạo kết quả tại đây.
    return null;
}
```

Đây là đoạn minh họa phương thức, chưa phải chương trình độc lập.

| Tham số | Cách đọc trong bài |
| --- | --- |
| `module` | Module của lớp đang được xử lý |
| `loader` | Bộ nạp định nghĩa lớp; có thể là `null` với bootstrap loader |
| `className` | Tên dạng nội bộ, ví dụ `demo/app/Target` |
| `classBeingRedefined` | `null` khi nạp lần đầu |
| `protectionDomain` | Thông tin miền bảo vệ của lớp |
| `classfileBuffer` | Dữ liệu lớp đầu vào của lượt gọi này |

Kết quả có hai ý nghĩa:

- `null`: transformer không thay đổi đầu vào.
- `byte[]` mới chứa class file hợp lệ: dùng kết quả đó cho bước tiếp theo.

Không sửa trực tiếp `classfileBuffer`. Không trả mảng rỗng để biểu thị “bỏ qua”. API còn có dạng năm tham số; dạng nhận `Module` mặc định gọi dạng đó. Ví dụ trong bài chủ động ghi đè dạng sáu tham số. Xem [hợp đồng ClassFileTransformer](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).

## 3. Thí nghiệm: thay byte lớp bằng bản đã biên dịch

Để quan sát cơ chế mà không cần thư viện xử lý bytecode, ta chuẩn bị hai bản của cùng lớp `demo.app.Target`:

| Bản | Giá trị message() trả về |
| --- | --- |
| Bản trong ứng dụng | `ORIGINAL` |
| Bản thay thế được agent giữ như tài nguyên | `AGENT` |

Đây là thí nghiệm thay cả dữ liệu lớp. Trong công cụ thực tế, thường cần đọc đầu vào hiện có rồi chỉnh đúng phần cần thay, để giữ phần còn lại và phối hợp với các agent khác.

### 3.1. Cây mã nguồn

Tạo một thư mục làm việc riêng, các tệp lưu UTF-8 không BOM:

```text
transform-demo/
├── agent.mf
├── src/
│   └── demo/
│       ├── agent/
│       │   └── LoadAgent.java
│       └── app/
│           ├── Main.java
│           └── Target.java
└── replacement-src/
    └── demo/
        └── app/
            └── Target.java
```

Hai tệp `Target.java` có cùng tên lớp đầy đủ, nên phải biên dịch vào **hai thư mục đầu ra riêng**. Không đặt cả hai vào cùng một lượt biên dịch.

### 3.2. Lớp gốc của ứng dụng

Tệp `src/demo/app/Target.java`:

```java
package demo.app;

public class Target {
    static {
        System.out.println("target.init");
    }

    public static String message() {
        return "ORIGINAL";
    }
}
```

Tệp `src/demo/app/Main.java`:

```java
package demo.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("app.main");
        System.out.println("result=" + Target.message());
    }
}
```

Dòng `target.init` giúp phân biệt thời điểm biến đổi với thời điểm khởi tạo lớp.

### 3.3. Lớp thay thế

Tệp `replacement-src/demo/app/Target.java`:

```java
package demo.app;

public class Target {
    static {
        System.out.println("target.init");
    }

    public static String message() {
        return "AGENT";
    }
}
```

Bản này giữ nguyên package, tên lớp và chữ ký phương thức mà `Main` cần dùng. Trong thí nghiệm, chỉ nội dung chuỗi trả về thay đổi.

### 3.4. Agent và transformer

Tệp `src/demo/agent/LoadAgent.java`:

```java
package demo.agent;

import java.io.InputStream;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public class LoadAgent {
    public static void premain(String options, Instrumentation inst) throws Exception {
        byte[] replacement;
        try (InputStream in = LoadAgent.class.getResourceAsStream("/replacement/Target.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing replacement/Target.class");
            }
            replacement = in.readAllBytes();
        }
        inst.addTransformer(new TargetTransformer(replacement));
        System.out.println("agent.ready");
    }

    private static final class TargetTransformer implements ClassFileTransformer {
        private final byte[] replacement;

        TargetTransformer(byte[] replacement) {
            this.replacement = replacement.clone();
        }

        @Override
        public byte[] transform(Module module, ClassLoader loader, String className,
                Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {
            if (!"demo/app/Target".equals(className) || classBeingRedefined != null) {
                return null;
            }
            System.out.println("transform=" + className);
            System.out.println("classBeingRedefined=" + classBeingRedefined);
            return replacement.clone();
        }
    }
}
```

Đọc mã theo thứ tự:

1. `premain` đọc byte thay thế **trước khi đăng ký** transformer.
2. Tài nguyên có đường dẫn `/replacement/Target.class`; đọc nó như dữ liệu không đồng nghĩa định nghĩa lớp `demo.app.Target`.
3. Bộ lọc chỉ chấp nhận `demo/app/Target` và trường hợp nạp lần đầu.
4. Những lớp khác nhận `null` ngay.
5. Với lớp đích, transformer trả một bản sao của dữ liệu thay thế; không ghi vào mảng đầu vào.

So sánh chuỗi bằng `"demo/app/Target".equals(className)` cũng tránh việc gọi phương thức trên một tham chiếu tên lớp có thể không có giá trị. Không cần dùng `Target.class` hay `Class.forName("demo.app.Target")` để kiểm tra tên: làm vậy có thể khiến lớp đích bị nạp quá sớm hoặc gây nạp lớp ngay trong quá trình biến đổi.

Mã mẫu lọc theo tên để giữ thí nghiệm ngắn. Nếu ứng dụng có nhiều bộ nạp cùng định nghĩa tên này, cần lọc thêm `loader` hoặc ngữ cảnh module theo mục tiêu thực tế; một tên lớp riêng lẻ chưa mô tả đầy đủ danh tính kiểu trong JVM.

### 3.5. Manifest và lệnh dựng

Tệp `agent.mf`, có dòng trống cuối:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.LoadAgent

```

Mở PowerShell tại `transform-demo`, dùng JDK 17 trở lên có `javac`, `jar`, `java` trong `PATH`:

```powershell
New-Item -ItemType Directory -Force out/agent, out/app, out/replacement, out/resources/replacement, dist | Out-Null

javac --release 17 -d out/agent src/demo/agent/LoadAgent.java
javac --release 17 -d out/app src/demo/app/Target.java src/demo/app/Main.java
javac --release 17 -d out/replacement replacement-src/demo/app/Target.java

Copy-Item -LiteralPath out/replacement/demo/app/Target.class -Destination out/resources/replacement/Target.class

jar --create --file dist/load-agent.jar --manifest agent.mf -C out/agent . -C out/resources .
```

Chỉ tiếp tục sau khi từng lệnh thành công. Tài nguyên thay thế được chép vào `replacement/Target.class`, không đặt tại mục `demo/app/Target.class` của JAR agent. Nhờ cách bố trí này, ta không vô tình đưa bản thay thế vào cùng đường tìm lớp theo đúng tên của lớp ứng dụng.

JAR agent chứa các mục cần thiết:

```text
META-INF/MANIFEST.MF
demo/agent/LoadAgent.class
demo/agent/LoadAgent$TargetTransformer.class
replacement/Target.class
```

Đây là các mục chính, không liệt kê mục thư mục. Kiểm tra bằng:

```powershell
jar --list --file dist/load-agent.jar
```

### 3.6. Chạy đối chứng

Không có agent:

```powershell
java -cp out/app demo.app.Main
```

Stdout:

```text
app.main
target.init
result=ORIGINAL
```

Có agent:

```powershell
java '-javaagent:dist/load-agent.jar' -cp out/app demo.app.Main
```

Stdout:

```text
agent.ready
app.main
transform=demo/app/Target
classBeingRedefined=null
target.init
result=AGENT
```

Cả hai lượt chạy đã được kiểm chứng bằng OpenJDK 24.0.2, mã biên dịch với `--release 17`.

Trong lượt chạy quan sát được, `Main.main` đã bắt đầu nhưng `Target` chưa được định nghĩa cho đến điểm cần dùng. `transform` nhận `classBeingRedefined=null`, trả byte mới, rồi mới thấy khối khởi tạo `target.init` và kết quả `AGENT`.

Mã trên đĩa không đổi. Chạy lại lệnh không có agent vẫn cho `ORIGINAL`. Nếu gọi `Target.message()` thêm lần nữa sau đó, không nên chờ thêm một lượt `transform` chỉ vì có thêm lời gọi phương thức.

## 4. Khi có nhiều transformer

Ví dụ ba transformer Java A, B, C cùng được đăng ký bằng `addTransformer(transformer)` theo thứ tự đó:

```text
B0 -> A trả byte mới B1 -> B trả null -> C nhận B1 -> kết quả cuối
```

`null` của B giữ nguyên đầu vào lượt B; nó không khôi phục B0 và không xóa kết quả A. Transformer phía sau nhìn thấy kết quả phía trước.

Không khái quát rằng mọi transformer trong JVM luôn theo một thứ tự đăng ký chung: API phân nhóm theo khả năng retransformation và loại Java/native; thứ tự đăng ký áp dụng **trong từng nhóm**. Với các transformer Java cùng nhóm trong ví dụ, thứ tự A → B → C là phù hợp. Xem [quy tắc ghép chuỗi biến đổi](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).

Thí nghiệm ở trên trả bản lớp chuẩn bị sẵn, bỏ qua dữ liệu hiện tại của lớp đích. Vì vậy, nếu transformer trước đã chỉnh lớp đó, cách thay cả bản lớp có thể làm mất chỉnh sửa trước. Đây là giới hạn có chủ ý để thấy rõ đường đi byte, không phải mẫu xử lý chung cho nhiều agent.

## 5. Lỗi cần nhận ra trước khi áp dụng

| Lỗi | Hệ quả hoặc hướng sửa |
| --- | --- |
| So `className` với `demo.app.Target` | Không trúng bộ lọc; tên nội bộ dùng dấu `/` |
| Đăng ký sau khi lớp đích đã nạp | Không tự có lại sự kiện nạp đầu tiên |
| Sửa mảng `classfileBuffer` tại chỗ | Vi phạm hợp đồng đầu vào |
| Trả byte của lớp có tên khác | Byte không còn mô tả đúng lớp đang định nghĩa |
| Đặt bản thay thế lên classpath trước bản gốc | Có thể đang chạy bản thay thế trực tiếp, không chứng minh transformer hoạt động |
| Tưởng callback chạy trên mỗi lời gọi | Thiết kế sai phép đo thời gian hoặc đếm lượt gọi |
| Quét/thay chuỗi tùy ý trong toàn bộ class file | Có thể làm hỏng cấu trúc hoặc thay dữ liệu không liên quan |

Transformer có thể được gọi từ các luồng nạp lớp khác nhau. Hãy giữ trạng thái dùng chung an toàn; ví dụ dùng mảng riêng không sửa sau khởi tạo và trả bản sao. Tránh đọc mạng, chờ khóa dài hoặc ghi log quá nhiều ngay trên đường nạp lớp. Mã xử lý biến đổi cũng có thể cần nạp lớp phụ trợ, nên cần kiểm soát phạm vi và chuẩn bị phụ trợ trước khi đăng ký.

Ngoại lệ do transformer ném ra không phải cách đáng tin để chặn nạp lớp: các transformer sau vẫn được gọi và JVM vẫn thử nạp. Ngược lại, byte trả về sai có thể làm quá trình kiểm tra/định nghĩa lớp thất bại. Phải phân biệt “mã transformer gặp lỗi” với “transformer tạo ra class file lỗi”; xem [quy tắc lỗi của transformer](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).

## 6. Tự thực hành

- Đổi nhánh xử lý lớp đích thành `return null`, dựng lại JAR rồi chạy: kết quả phải trở về `ORIGINAL`.
- Thêm lần gọi `Target.message()` thứ hai trong `Main`: phân biệt số lần thực thi phương thức với số lần định nghĩa lớp.
- Viết sai bộ lọc thành `demo.app.Target`: giải thích vì sao không thấy hai dòng `transform=...` và `classBeingRedefined=...`.
- Kiểm tra JAR và classpath để chứng minh bản `AGENT` chỉ được đọc như tài nguyên trước khi transformer trả nó.

Khi giải thích được mỗi mũi tên từ byte gốc đến byte cuối, bạn đã có cơ sở để đọc các công cụ chèn bytecode phức tạp hơn mà không nhầm giữa nạp lớp, khởi tạo lớp và thực thi phương thức.
