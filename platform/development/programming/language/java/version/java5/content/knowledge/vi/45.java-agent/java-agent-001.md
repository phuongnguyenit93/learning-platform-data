# java.lang.instrument: quan sát và biến đổi bytecode bằng Java agent

## 1. Khái niệm: agent nằm ở đâu trong quá trình chạy?

Một chương trình Java thường đi qua chuỗi:

```text
Mã nguồn .java → javac → dữ liệu .class → JVM định nghĩa lớp → thực thi phương thức
```

`java.lang.instrument` cung cấp các API để một **Java agent** tham gia vào quá trình này. Agent là mã Java được JVM khởi động theo giao thức riêng; agent có thể nhận dữ liệu lớp trước khi JVM định nghĩa lớp, quan sát thông tin hoặc cung cấp dữ liệu lớp đã biến đổi.

**Bytecode** là các lệnh JVM trong phương thức. Một dữ liệu `.class` hoàn chỉnh còn chứa tên lớp, bảng hằng, mô tả phương thức, trường và các thuộc tính khác. Transformer nhận và trả **toàn bộ dữ liệu ở định dạng class file**, không chỉ một chuỗi lệnh của một phương thức.

Các vai trò cần phân biệt:

| Thành phần | Trách nhiệm |
| --- | --- |
| Ứng dụng | Thực hiện chức năng nghiệp vụ |
| Java agent | Khởi tạo công cụ quan sát hoặc biến đổi trong cùng JVM |
| `Instrumentation` | Đối tượng JVM cấp cho agent để đăng ký transformer và gọi các khả năng hỗ trợ |
| `ClassFileTransformer` | Nhận dữ liệu lớp tại các sự kiện phù hợp; trả dữ liệu thay thế hoặc `null` |
| Công cụ xử lý bytecode | Đọc và tạo class file đúng định dạng; là một phần có thể được agent sử dụng |

Agent không phải một tiến trình khác, một lớp cha bắt buộc của ứng dụng hay một cơ chế sửa trực tiếp mã nguồn. Trong ví dụ bài này, ứng dụng không gọi API của agent; JVM gọi điểm vào của agent trước `main`.

API nền tảng này xuất hiện từ Java 5 và vẫn được sử dụng trên JDK hiện đại. Bài dùng JDK 17+ để thực hành, ưu tiên khởi động bằng `-javaagent`, không dựa vào cơ chế tự gắn agent vào JVM đang chạy.

## 2. Vì sao công cụ cần quan sát hoặc biến đổi lớp?

Giả sử muốn biết một phương thức xử lý yêu cầu mất bao lâu. Có thể sửa từng phương thức để thêm bộ đếm thời gian, nhưng làm vậy trên nhiều lớp hoặc thư viện bên ngoài sẽ khó duy trì.

Một agent có thể chọn các lớp cần đo, rồi thêm lệnh lấy thời gian vào đầu và cuối những phương thức phù hợp. Khi ứng dụng gọi phương thức, chính các lệnh đã thêm sẽ thu thập số liệu.

Hai mục đích phải được tách rõ:

- **Quan sát sự kiện lớp:** nhận tên lớp, bộ nạp lớp hoặc kích thước mảng dữ liệu lớp; không thay đổi dữ liệu, trả `null`.
- **Biến đổi để quan sát khi thực thi:** thêm lệnh vào thân phương thức để đếm số lần gọi, ghi sự kiện, tính thời gian hoặc ghi nhận dòng mã đã chạy.

Trường hợp thứ hai vẫn có biến đổi bytecode, dù mục tiêu là quan sát và giữ kết quả nghiệp vụ như cũ. Việc đo có thể làm tăng thời gian chạy hoặc bộ nhớ; không được hiểu “quan sát” là tuyệt đối không có tác động.

Ví dụ ứng dụng của cách tiếp cận này gồm đo hiệu năng, thu thập dấu vết xử lý, đo độ bao phủ kiểm thử và ghi nhận sự kiện. Tuy nhiên, **chỉ đăng ký transformer không tự tạo ra dữ liệu ở mức phương thức**. Phải có logic biến đổi thích hợp hoặc một cơ chế quan sát khác.

## 3. Cơ chế khi khởi động bằng -javaagent

Một agent JAR khai báo lớp khởi động trong manifest:

```text
Premain-Class: demo.Agent
```

JVM gọi phương thức sau trước `main` của ứng dụng:

```java
public static void premain(String agentArgs, Instrumentation instrumentation)
```

`agentArgs` là chuỗi tùy chọn sau dấu `=` trong `-javaagent:agent.jar=options`. Agent tự phân tích chuỗi này. Đối tượng `Instrumentation` do JVM cung cấp; ứng dụng không tạo một đối tượng thay thế bằng `new`.

Luồng nạp lớp có thể hình dung như sau:

```text
JVM khởi động
    ↓
premain đăng ký transformer
    ↓
Ứng dụng yêu cầu nạp lớp đích
    ↓
transform nhận dữ liệu lớp
    ├─ trả null: không thay đổi tại transformer này
    └─ trả byte[] mới: cung cấp dữ liệu lớp thay thế
    ↓
JVM kiểm tra và định nghĩa lớp
    ↓
Ứng dụng sử dụng lớp
```

`transform` chạy trong quá trình xử lý dữ liệu lớp; nó không được gọi mỗi lần một phương thức của lớp chạy. Khi đã nạp lớp xong, gọi cùng phương thức một nghìn lần không đồng nghĩa transformer sẽ chạy thêm một nghìn lần.

Với nhiều transformer, kết quả của transformer trước có thể là đầu vào của transformer sau. Vì vậy, `return null` nghĩa là **transformer này không thay đổi đầu vào**, không có nghĩa khôi phục dữ liệu nguyên thủy hay hủy thay đổi của công cụ khác. Thứ tự còn phụ thuộc nhóm transformer có hỗ trợ biến đổi lại hay không; không nên giả định mọi công cụ chỉ được xếp theo thứ tự đăng ký toàn cục.

### Hợp đồng quan trọng của transform

Bài dùng dạng phương thức sau; đây là chữ ký minh họa, chưa phải chương trình độc lập:

```java
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
```

- `className` dùng dạng nội bộ như `demo/Greeting`, không phải `demo.Greeting`. Lọc bằng `"demo/Greeting".equals(className)` cũng tránh lỗi khi tên là `null`.
- `loader` xác định bộ nạp lớp; giá trị có thể là `null` đối với bộ nạp bootstrap.
- `classBeingRedefined` là `null` khi nạp lần đầu; khác `null` khi đang định nghĩa lại hoặc biến đổi lại.
- `classfileBuffer` là dữ liệu đầu vào. **Không sửa trực tiếp mảng này.**
- Trả `null` nếu không biến đổi. Nếu biến đổi, trả một mảng mới chứa class file hợp lệ; không trả mảng rỗng và không trả byte của mã nguồn `.java`.

JDK hiện đại còn có dạng `transform` nhận thêm `Module`. Ví dụ dưới đây dùng dạng không có tham số `Module`, vẫn được hỗ trợ. Không dùng lambda cho `ClassFileTransformer`: đây không phải giao diện hàm theo định nghĩa API hiện đại.

## 4. Thí nghiệm: cùng ứng dụng, ba cách chạy

Thí nghiệm sẽ chứng minh:

1. Không dùng agent: ứng dụng in lời chào gốc.
2. Agent chỉ quan sát: transformer nhận lớp đích, lời chào giữ nguyên.
3. Agent thay dữ liệu lớp trước khi định nghĩa: ứng dụng in lời chào khác.

Để nhìn rõ hợp đồng `byte[]`, ví dụ không tự phân tích class file và không dùng thư viện bên ngoài. Ta biên dịch sẵn hai phiên bản của cùng lớp `demo.Greeting`. Agent dùng byte của phiên bản thứ hai làm dữ liệu thay thế.

Đây là mô hình minh họa luồng biến đổi; không phải cách tổng quát để chèn mã vào mọi lớp. Nó cố ý thay thông điệp trả về nhằm tạo khác biệt dễ kiểm chứng.

### 4.1. Tạo các tệp

Tạo cấu trúc sau trong một thư mục thực hành riêng:

```text
src/
└── demo/
    ├── Agent.java
    ├── App.java
    └── Greeting.java
replacement-src/
└── demo/
    └── Greeting.java
MANIFEST.MF
```

**Tệp `src/demo/Agent.java`:**

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class Agent {
    public static void premain(String args, Instrumentation instrumentation)
            throws IOException {
        byte[] replacement = "replace".equals(args) ? readReplacement() : null;
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> classBeingRedefined, ProtectionDomain domain,
                    byte[] classfileBuffer) {
                if (!"demo/Greeting".equals(className)) {
                    return null;
                }
                if (replacement == null) {
                    System.out.println("[agent] observe demo/Greeting");
                    return null;
                }
                System.out.println("[agent] replace demo/Greeting");
                return replacement.clone();
            }
        });
        System.out.println("[agent] registered");
    }

    private static byte[] readReplacement() throws IOException {
        try (InputStream input = Agent.class.getResourceAsStream(
                "/replacement/Greeting.class")) {
            if (input == null) {
                throw new IllegalStateException("Missing replacement bytes");
            }
            return input.readAllBytes();
        }
    }
}
```

Agent chỉ chọn đúng tên lớp của thí nghiệm. Dữ liệu thay thế được đọc trước lúc đăng ký transformer; callback không mở tệp mỗi lần nhận sự kiện. `clone()` tạo mảng trả về riêng, còn `classfileBuffer` không bị sửa.

**Tệp `src/demo/App.java`:**

```java
package demo;

public final class App {
    public static void main(String[] args) throws Exception {
        System.out.println("[app] main");
        Class<?> greeting = Class.forName("demo.Greeting");
        Object message = greeting.getMethod("message").invoke(null);
        System.out.println(message);
    }
}
```

Ứng dụng dùng tên lớp dạng chuỗi rồi mới nạp lớp sau dòng in đầu tiên, giúp thứ tự quan sát trong thí nghiệm rõ ràng. Reflection ở đây chỉ phục vụ việc kiểm soát thời điểm nạp; agent không yêu cầu mọi ứng dụng phải gọi phương thức bằng reflection.

**Tệp `src/demo/Greeting.java`:**

```java
package demo;

public final class Greeting {
    public static String message() {
        return "Hello from application";
    }
}
```

**Tệp `replacement-src/demo/Greeting.java`:**

```java
package demo;

public final class Greeting {
    public static String message() {
        return "Hello from agent";
    }
}
```

Hai tệp có cùng tên nhị phân `demo.Greeting`; phải biên dịch vào hai thư mục đầu ra khác nhau, không biên dịch chung như hai lớp khác nhau trong một lần gọi `javac`.

**Tệp `MANIFEST.MF`:**

```text
Manifest-Version: 1.0
Premain-Class: demo.Agent

```

Lưu manifest dạng văn bản thông thường, kết thúc dòng cuối bằng ký tự xuống dòng; có một dòng trống cuối tệp như minh họa. Không đặt `Main-Class` thay cho `Premain-Class`: ứng dụng và agent có điểm vào khác nhau.

### 4.2. Biên dịch và đóng gói

Cần bộ JDK có `java`, `javac`, `jar` trên `PATH`. Chạy các lệnh từ thư mục chứa `src`, `replacement-src` và manifest.

Các lệnh biên dịch/đóng gói sau dùng được trong PowerShell:

```powershell
javac --release 17 -d agent-classes src/demo/Agent.java
javac --release 17 -d app-classes src/demo/App.java src/demo/Greeting.java
javac --release 17 -d replacement-classes replacement-src/demo/Greeting.java

New-Item -ItemType Directory -Force -Path agent-resources/replacement | Out-Null
Copy-Item -LiteralPath replacement-classes/demo/Greeting.class -Destination agent-resources/replacement/Greeting.class

jar --create --file observer-agent.jar --manifest MANIFEST.MF -C agent-classes . -C agent-resources .
```

Chỉ tiếp tục khi từng lệnh thành công. `--release 17` tạo dữ liệu lớp tương thích Java 17 và giới hạn API theo phiên bản đó, kể cả khi đang dùng JDK mới hơn.

Trong agent JAR, dữ liệu thay thế nằm tại `replacement/Greeting.class`, là một tài nguyên do agent đọc. Nó không nằm tại `demo/Greeting.class`, nên không được vô tình chọn như lớp ứng dụng từ agent JAR. Thư mục `replacement-classes` cũng không được thêm vào classpath khi chạy ứng dụng.

### 4.3. Chạy không có agent

```powershell
java -cp app-classes demo.App
```

Stdout:

```text
[app] main
Hello from application
```

### 4.4. Chạy agent ở chế độ quan sát

```powershell
java "-javaagent:observer-agent.jar" -cp app-classes demo.App
```

Stdout:

```text
[agent] registered
[app] main
[agent] observe demo/Greeting
Hello from application
```

JVM gọi `premain` trước `main`. Khi `Class.forName` yêu cầu lớp đích, transformer in tên rồi trả `null`. Ứng dụng vẫn nhận dữ liệu lớp gốc.

### 4.5. Chạy agent ở chế độ thay thế

```powershell
java "-javaagent:observer-agent.jar=replace" -cp app-classes demo.App
```

Stdout:

```text
[agent] registered
[app] main
[agent] replace demo/Greeting
Hello from agent
```

Chuỗi `replace` được truyền vào `premain`. Callback trả dữ liệu lớp thay thế trước khi JVM định nghĩa `demo.Greeting`. Ứng dụng vẫn tìm cùng lớp và gọi cùng phương thức, nhưng thân phương thức được JVM sử dụng là phiên bản đã thay thế.

Ba luồng trên đã được biên dịch với `--release 17` và kiểm tra bằng JDK 24.0.2. Các khối kết quả chỉ mô tả stdout của chương trình trong cấu hình một agent của bài.

### 4.6. Kiểm tra agent có sửa tệp trên đĩa không

Chạy lại lệnh không có agent:

```powershell
java -cp app-classes demo.App
```

Stdout trở lại:

```text
[app] main
Hello from application
```

Agent của thí nghiệm không ghi lại `app-classes/demo/Greeting.class`. Thay đổi chỉ áp dụng cho dữ liệu mà JVM dùng trong lần chạy có agent. Một công cụ có thể chủ động xuất dữ liệu ra đĩa nếu được lập trình như vậy, nhưng đó không phải tác dụng tự động của `ClassFileTransformer`.

## 5. Từ thay lời chào đến đo thời gian thực thi

Muốn đo một phương thức thật, công cụ thường cần biến đổi thân phương thức theo ý tưởng:

```text
Trước:
    xử lý nghiệp vụ

Sau:
    lấy thời điểm bắt đầu
    thử:
        xử lý nghiệp vụ
    cuối cùng:
        ghi nhận khoảng thời gian
```

Đây là mô hình minh họa, không phải Java hoàn chỉnh. Một bộ biến đổi thực tế cần xử lý đúng đường `return`, ngoại lệ, kiểu dữ liệu trên ngăn xếp, bảng stack map và liên kết tới mã hỗ trợ. Nếu bỏ sót nhánh ném ngoại lệ, phép đo có thể không ghi nhận các lần gọi thất bại.

`java.lang.instrument` cung cấp điểm can thiệp và thao tác với JVM; nó không cung cấp sẵn một hàm “chèn bộ đếm vào mọi phương thức”. Thư viện xử lý bytecode có thể giúp đọc/ghi cấu trúc lớp, nhưng vẫn phải tuân theo hợp đồng của JVM.

Mã hỗ trợ do agent chèn vào cũng phải được lớp đích nhìn thấy qua bộ nạp lớp và quy tắc module phù hợp. Chạy được với một ứng dụng classpath đơn giản chưa chứng minh hoạt động đúng với nhiều bộ nạp lớp hoặc named module.

Khác với cơ chế proxy chỉ nhận những lời gọi đi qua proxy, mã được chèn nằm trong thân phương thức đích. Tuy nhiên, agent chỉ tác động các lớp/phương thức thực sự được chọn và biến đổi; nó không mặc nhiên bao phủ toàn bộ ứng dụng.

## 6. Lớp đã nạp và các khả năng liên quan

Đăng ký transformer không tự biến đổi ngược mọi lớp đã nạp. Phân biệt ba tình huống:

| Tình huống | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| Biến đổi khi nạp lần đầu | Cung cấp dữ liệu trước khi JVM định nghĩa lớp | Transformer phải được đăng ký trước sự kiện phù hợp |
| `retransformClasses` | Yêu cầu JVM thực hiện lại quy trình biến đổi cho lớp đã nạp | JVM hỗ trợ, manifest phù hợp, lớp sửa được; transformer cần đăng ký với khả năng biến đổi lại để callback của nó được gọi trong quy trình này |
| `redefineClasses` | Cung cấp dữ liệu định nghĩa thay thế cho lớp đã nạp | JVM hỗ trợ, manifest phù hợp và tuân thủ giới hạn định nghĩa lại |

Hai thao tác ở hàng cuối là kiến thức mở rộng vẫn áp dụng trên JDK hiện đại; thí nghiệm không sử dụng chúng và không cần khai báo khả năng tương ứng trong manifest. `retransformClasses` được thêm từ Java 6, không phải toàn bộ API trong bảng đều đã có ngay ở Java 5.

Biến đổi lại không nên được hiểu là luôn nhận đúng từng byte của kết quả trước đó. JVM tái xây dựng đầu vào theo hợp đồng của API; kết quả từ các transformer không có khả năng biến đổi lại được tái sử dụng. Logic biến đổi phải được thiết kế cho quy trình đó.

Định nghĩa lại/biến đổi lại lớp đã nạp có giới hạn; không dùng chúng như một cơ chế tổng quát để thêm/xóa trường, đổi chữ ký phương thức hoặc thay hệ phân cấp lớp. Khung thực thi đang chạy cũng không tự quay về đầu để chạy thân phương thức mới.

Một số thao tác quan sát khác của `Instrumentation` là `getAllLoadedClasses()`, `getInitiatedClasses(loader)` và `getObjectSize(object)`. Đặc biệt, `getObjectSize` chỉ cho ước lượng kích thước của chính đối tượng theo cách triển khai JVM; không tự duyệt toàn bộ đồ thị đối tượng để cho kích thước bộ nhớ được giữ lại.

## 7. Điểm cần lưu ý và lỗi phổ biến

### Lọc sai tên hoặc bỏ qua bộ nạp lớp

`demo.Greeting` và `demo/Greeting` không dùng thay thế nhau trong mọi API. `Class.forName` dùng tên nhị phân có dấu chấm; callback transformer nhận tên dạng nội bộ có dấu gạch chéo.

Ngoài ra, hai lớp cùng tên do hai bộ nạp khác nhau định nghĩa là hai lớp khác nhau. Bộ lọc chỉ dựa trên tên như thí nghiệm phù hợp phạm vi rất nhỏ; công cụ thực tế có thể cần xét thêm `loader`, module và nguồn lớp.

### Trả dữ liệu không hợp lệ

JVM vẫn kiểm tra dữ liệu lớp đầu ra. Sai tên lớp, phiên bản class file không tương thích, lệnh bytecode sai kiểu hoặc thông tin kiểm tra không hợp lệ có thể dẫn tới lỗi khi định nghĩa hay liên kết lớp. Không thay chuỗi tùy tiện trong mảng byte rồi giả định class file vẫn đúng.

Không sửa trực tiếp đầu vào của transformer. Việc trả `null` cũng không “chặn nạp lớp”. Ngoại lệ do transformer ném ra không phải cơ chế đáng tin cậy để từ chối nạp lớp: quá trình còn có thể tiếp tục qua các transformer khác.

### Làm quá nhiều việc trong callback

Việc nạp lớp có thể diễn ra đồng thời. Trạng thái dùng chung của transformer phải được xử lý phù hợp với nhiều luồng; không giả định chỉ có một luồng ứng dụng gọi vào.

Tránh I/O chậm, truy cập mạng, khóa dùng chung phức tạp hoặc chủ động nạp chính lớp đang được biến đổi. Đặc biệt, biến đổi lớp nền tảng mà chính agent phụ thuộc có thể tạo vòng lặp nạp/liên kết lớp. `System.out.println` trong bài chỉ là phương tiện quan sát một lớp đích nhỏ, không phải thiết kế ghi log có tải cao.

### Chỉ đo đường chạy thành công

Khi chèn logic đo, cần xác định rõ cách xử lý ngoại lệ, đệ quy và lời gọi lồng nhau. Dữ liệu thu được chỉ có ý nghĩa khi phép đo có định nghĩa rõ: thời gian toàn bộ lời gọi, thời gian CPU hay một đại lượng khác. Callback lúc nạp lớp không trả lời trực tiếp các câu hỏi đó.

### Đồng nhất khởi động agent với nạp agent động

`-javaagent` khởi động agent cùng JVM qua `premain`. Nạp agent vào JVM đang chạy là một luồng khác, gắn với `agentmain` và khả năng/chính sách của môi trường. Không giả định cách gắn động luôn được bật hoặc không có cảnh báo trên JDK hiện đại. Bài này không cần Attach API hay tùy chọn cho phép nạp agent động.

### Xem agent như một cấu hình không có ảnh hưởng

Agent chạy trong JVM của ứng dụng và có thể thay đổi mã được thực thi. Hãy xác minh nguồn agent, đo chi phí và thử nghiệm tương tác khi dùng nhiều agent. Nếu `premain` của agent khởi động bằng `-javaagent` không thể khởi tạo đúng hoặc ném lỗi không được xử lý, JVM có thể dừng trước khi ứng dụng vào `main`.

## 8. Thực hành tự kiểm chứng

1. Trong `App`, gọi `message` hai lần sau khi đã có đối tượng `Class`. Dự đoán transformer in bao nhiêu lần, rồi chạy kiểm tra. Với thí nghiệm nạp lớp một lần và không có yêu cầu biến đổi lại, dòng observe/replace xuất hiện một lần; lời chào xuất hiện hai lần.
2. Đổi bộ lọc của agent thành `"demo.Greeting".equals(className)`. Giải thích vì sao không còn dòng quan sát lớp đích và chế độ `replace` không đổi lời chào.
3. Bỏ `-javaagent` khỏi lệnh chạy, giữ nguyên mọi tệp đã biên dịch. Kiểm tra ứng dụng vẫn chạy với lời chào gốc.
4. Chỉ ra cần thêm phần nào nếu muốn đếm số lần gọi `message`. Câu trả lời phải có mã được chèn vào thân phương thức hoặc một cơ chế đo khác; đếm số lần callback `transform` không đo được số lần gọi phương thức.
5. Giải thích vì sao phiên bản `Greeting.class` thay thế được đặt dưới đường dẫn tài nguyên `replacement/`, thay vì thêm nguyên thư mục `replacement-classes` vào classpath.

Sau thí nghiệm, cần phân biệt được ba việc: **nhận sự kiện dữ liệu lớp**, **thay dữ liệu trước khi JVM định nghĩa lớp** và **thu thập số liệu khi phương thức thực thi**. Hai việc đầu do ví dụ trực tiếp chứng minh; việc thứ ba cần thêm logic biến đổi phù hợp.

## Tài liệu đối chiếu

- [Đặc tả java.lang.instrument trên JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): cách JVM khởi động agent và các điểm vào.
- [ClassFileTransformer](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): hợp đồng đầu vào/đầu ra và thời điểm callback.
- [Instrumentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký transformer, biến đổi lại và các khả năng hỗ trợ.
