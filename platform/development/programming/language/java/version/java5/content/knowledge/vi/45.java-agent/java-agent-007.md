# Đăng ký, gỡ transformer và xử lý lỗi

## 1. Quản lý vòng đời của một bộ biến đổi

Một bộ biến đổi lớp (`ClassFileTransformer`, thường gọi là transformer) là đối tượng được agent đăng ký với JVM để nhận bytecode trong quá trình định nghĩa hoặc thay đổi lớp. Nó có thể phân tích dữ liệu, trả về bytecode mới hoặc quyết định không thay đổi gì.

Vòng đời cần quản lý gồm:

```text
tạo đối tượng
    -> chuẩn bị cấu hình và tài nguyên
        -> đăng ký với Instrumentation
            -> nhận các lời gọi transform
                -> vô hiệu hóa theo thiết kế của agent
                    -> gỡ đăng ký
```

Có ba việc khác nhau: **gỡ đăng ký**, **đợi lời gọi đang chạy hoàn tất** và **khôi phục các lớp đã thay đổi**. `removeTransformer` chỉ thực hiện việc đầu tiên theo hợp đồng API; không tự làm hai việc còn lại.

Bài dùng API và ví dụ Java 17+, tập trung vòng đời và xử lý lỗi. Ví dụ không sửa bytecode để dễ quan sát sự kiện đăng ký, gọi và gỡ.

## 2. Đăng ký đúng đối tượng, đúng khả năng

Hai dạng đăng ký:

```java
inst.addTransformer(transformer);
inst.addTransformer(transformer, canRetransform);
```

Đây là các lời gọi minh họa ở nơi đã có `Instrumentation inst` và một đối tượng `transformer`.

Dạng một tham số tương đương `addTransformer(transformer, false)`. Giá trị `false` không có nghĩa bộ biến đổi không hoạt động: nó vẫn tham gia xử lý định nghĩa lớp mới và định nghĩa lại lớp theo hợp đồng.

Giá trị `true` cho phép bộ biến đổi tham gia những lần retransformation. Muốn đăng ký dạng này, agent cần yêu cầu `Can-Retransform-Classes: true` trong manifest và kiểm tra `inst.isRetransformClassesSupported()`. Nếu khả năng không được hỗ trợ, đăng ký với `true` ném `UnsupportedOperationException`.

Đăng ký không tự làm các lớp đã nạp trước đó chạy lại bộ biến đổi. Nếu cần tác động các lớp đã nạp, phải chọn thao tác riêng, kiểm tra khả năng và lớp đích, đồng thời tuân thủ giới hạn thay đổi cấu trúc lớp.

Nên giữ tham chiếu tới chính đối tượng đã đăng ký để gỡ sau này. Không tạo một đối tượng mới chỉ có cùng cấu hình rồi mong JVM hiểu đó là đăng ký cũ.

Đăng ký cùng một instance nhiều lần là điều API cho phép nhưng nên tránh. Nó có thể khiến bộ biến đổi được gọi nhiều lần; một lần gỡ chỉ loại đăng ký khớp được thêm gần nhất, không quét sạch mọi lần đăng ký. `addTransformer(null)` và `removeTransformer(null)` đều ném `NullPointerException`. Xem [hợp đồng đăng ký và gỡ của Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).

## 3. Thứ tự gọi và dữ liệu chạy qua chuỗi

Khi có nhiều bộ biến đổi, kết quả của bộ trước trở thành đầu vào của bộ sau. Một bộ trả về `null` có nghĩa nó không đóng góp thay đổi trong lần gọi đó; các thay đổi từ bộ trước vẫn còn trong chuỗi.

Không suy luận mọi thứ theo một danh sách đăng ký duy nhất: JVM phân nhóm theo khả năng retransformation và có cả các bộ biến đổi native. Trong cùng nhóm, thứ tự đăng ký quyết định thứ tự gọi. Ví dụ ở phần thực hành dùng hai bộ biến đổi Java đều đăng ký với `false`, nên có thể quan sát chúng theo thứ tự `first` rồi `second`.

Khi thực hiện retransformation:

- Bộ biến đổi có khả năng retransformation được gọi lại.
- Với bộ không có khả năng đó, kết quả biến đổi trước được dùng lại theo hợp đồng API; phương thức `transform` của nó không được gọi lại trong bước này.

Mỗi bộ chỉ nên xử lý phạm vi lớp được thiết kế. Bộ lọc sớm theo tên lớp giúp giảm công việc và tránh agent tự tác động các lớp phục vụ chính nó.

Ở tham số `className`, tên lớp dùng dạng nội bộ như `demo/app/Target`, không phải `demo.app.Target`. Nên viết bộ lọc chịu được giá trị không phù hợp hoặc `null`, ví dụ gọi `"demo/app/Target".equals(className)`.

Bộ biến đổi không được sửa trực tiếp mảng `classfileBuffer` đầu vào. Khi cần thay đổi, tạo mảng byte kết quả riêng và bảo đảm class file hợp lệ. Chi tiết chuỗi xử lý xem [đặc tả ClassFileTransformer](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).

## 4. Gỡ đăng ký: kết quả boolean nói được điều gì?

Lời gọi:

```java
boolean removed = inst.removeTransformer(transformer);
```

- `true`: tìm thấy và gỡ được một đăng ký khớp.
- `false`: không tìm thấy đăng ký khớp để gỡ.

Kết quả `true` không chứng minh rằng mọi lời gọi `transform` đã hoàn tất. Nạp lớp có thể diễn ra trên nhiều luồng, và bộ biến đổi vẫn có thể nhận lời gọi sau khi bị gỡ do công việc đang diễn ra đồng thời.

Một cách phòng vệ là có cờ hoạt động dùng `volatile` hoặc `AtomicBoolean`:

```text
disable: đặt cờ false
transform: đọc cờ, nếu false thì trả null
remove: gỡ đăng ký khỏi Instrumentation
```

Cờ giúp các lời gọi quan sát trạng thái mới bỏ qua xử lý. Nó **không phải hàng rào chờ hoàn tất**: một lời gọi có thể đã đọc `true` rồi tiếp tục làm việc trong lúc luồng khác đặt `false`.

Nếu phải đóng tài nguyên mà callback còn dùng, cần thiết kế cơ chế quản lý các lời gọi đang hoạt động và thời điểm giải phóng tài nguyên. Không đóng ngay tài nguyên chỉ dựa vào `removed==true`. Cũng không giữ một khóa toàn cục trong `transform` rồi chờ vô hạn ở luồng gỡ; thiết kế đó có thể gây kẹt khi nạp lớp và khởi tạo phụ thuộc lẫn nhau.

Ngoài ra, gỡ đăng ký không hoàn tác lớp đã bị sửa. Nếu công cụ có chức năng khôi phục, đó là một quy trình riêng cần biết lớp nào đã đổi, những bộ biến đổi nào còn hoạt động và JVM hỗ trợ thao tác nào. Không hứa rằng “gỡ agent là ứng dụng trở về bytecode ban đầu”.

## 5. Phân biệt các nơi phát sinh lỗi

| Nơi phát sinh | Hậu quả và hướng xử lý |
| --- | --- |
| Trong lúc cấu hình/đăng ký ở `premain` | Ngoại lệ không được xử lý có thể làm JVM hủy khởi động; kiểm tra khả năng và xác thực cấu hình trước khi đăng ký |
| Trong `transform`, bộ biến đổi ném ngoại lệ | Các bộ biến đổi tiếp theo vẫn được gọi; JVM vẫn thử tiếp tục quá trình nạp/đổi lớp |
| Trả về bytecode sai định dạng hoặc không hợp lệ | JVM có thể từ chối lớp bằng lỗi định dạng, kiểm chứng hoặc liên kết; ứng dụng có thể bị ảnh hưởng |
| Gỡ một bộ không được đăng ký | Nhận `false`; đây không phải ngoại lệ |
| Bộ biến đổi kích hoạt nạp lớp gây vòng phụ thuộc | Có thể phát sinh lỗi liên kết hoặc vòng nạp lớp; cần sửa thiết kế phụ thuộc, không chỉ bắt ngoại lệ |

### Ngoại lệ trong transform không phải lệnh cấm nạp lớp

Nếu một bộ biến đổi ném ngoại lệ mà không xử lý, hiệu ứng của riêng bộ đó trong chuỗi tương tự trả về `null`; các bộ sau vẫn có cơ hội xử lý. Điều này không có nghĩa lớp chắc chắn nạp thành công: bytecode từ một bộ khác vẫn có thể không hợp lệ, hoặc có lỗi liên kết/khởi tạo ở giai đoạn khác.

Vì vậy, không dùng `throw new RuntimeException(...)` trong `transform` như cơ chế chặn chắc chắn ứng dụng hoặc chặn một lớp. Nếu agent có yêu cầu bắt buộc về độ bao phủ, cần thiết kế trạng thái sức khỏe và điều kiện khởi chạy ứng dụng riêng, rồi kiểm chứng đầy đủ.

`IllegalClassFormatException` phục vụ tình huống phát hiện dữ liệu class file đầu vào không hợp lệ; bản thân nó cũng không biến `transform` thành một cổng từ chối nạp lớp. Nó có ích cho chẩn đoán lỗi định dạng, kể cả dữ liệu đã bị bộ trước làm hỏng. Xem [ý nghĩa IllegalClassFormatException](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/IllegalClassFormatException.html).

### Không giấu việc công cụ đã thất bại

Công cụ đo đạc thường chọn để ứng dụng tiếp tục khi một phép biến đổi không thực hiện được. Khi đó phải ghi nhận đủ thông tin để biết phần nào không được đo, thay vì để dashboard trông như đang thu thập đầy đủ.

Ở biên của `transform`, có thể xử lý lỗi dự kiến của thư viện bytecode, ghi bộ đếm/thông tin chẩn đoán tối thiểu rồi trả về `null` theo chính sách. Nếu chọn bắt rộng `Throwable`, phải có chủ đích; không coi đó là cách an toàn để tiếp tục sau mọi lỗi nghiêm trọng của JVM.

Ghi log cũng có thể nạp thêm lớp, cấp phát bộ nhớ và gây lỗi. Nên chuẩn bị các phụ thuộc cần thiết trước khi đăng ký, lọc lớp sớm và giới hạn tần suất báo lỗi. Không gửi yêu cầu mạng hoặc khởi tạo cả một hệ thống logging nặng ngay trong mọi lần `transform`.

## 6. Ví dụ hoàn chỉnh: lỗi ở bộ trước, gỡ bộ sau

Ví dụ sử dụng hai bộ biến đổi:

- `first`: cố ý ném `IllegalStateException` khi thấy `Target`, để chứng minh chuỗi vẫn tiếp tục.
- `second`: chỉ ghi nhận hai lớp thử nghiệm và trả về `null`; ứng dụng gỡ nó trước khi nạp lớp thứ hai.

Đây là lỗi giả lập có chủ đích, không phải cách xử lý lỗi khuyến nghị trong agent thực tế.

### Cấu trúc tệp

```text
src/agent/demo/agent/LifecycleAgent.java
src/app/demo/app/Main.java
agent-manifest.mf
```

### Mã agent

Tệp `src/agent/demo/agent/LifecycleAgent.java`:

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicBoolean;

public final class LifecycleAgent {
    private static Instrumentation instrumentation;
    private static final Probe SECOND = new Probe("second", false);

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        inst.addTransformer(new Probe("first", true), false);
        inst.addTransformer(SECOND, false);
        System.out.println("agent: registered first, second");
    }

    public static boolean stopSecond() {
        SECOND.disable();
        return instrumentation.removeTransformer(SECOND);
    }

    private static final class Probe implements ClassFileTransformer {
        private final String label;
        private final boolean failOnTarget;
        private final AtomicBoolean enabled = new AtomicBoolean(true);

        private Probe(String label, boolean failOnTarget) {
            this.label = label;
            this.failOnTarget = failOnTarget;
        }

        private void disable() {
            enabled.set(false);
        }

        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {
            if (!enabled.get()) {
                return null;
            }
            if (!"demo/app/Target".equals(className)
                    && !"demo/app/OtherTarget".equals(className)) {
                return null;
            }
            if (failOnTarget && "demo/app/Target".equals(className)) {
                System.out.println(label + ": error on " + className);
                throw new IllegalStateException("simulated transformer failure");
            }
            System.out.println(label + ": saw " + className);
            return null;
        }
    }
}
```

Hai đối tượng `Probe` có cấu hình không đổi và cờ hoạt động nguyên tử. Hàm `stopSecond` vô hiệu hóa rồi gỡ **đúng instance** `SECOND`.

Đoạn mã chỉ có các lời gọi dừng từ luồng ứng dụng trong phép thử. Nếu sản phẩm cho nhiều luồng đồng thời đăng ký/gỡ, cần quản lý trạng thái điều khiển vòng đời riêng để tránh trùng đăng ký hoặc gỡ nhầm thời điểm.

Ví dụ dùng `System.out.println` sau bộ lọc rất hẹp để dễ học. Đây không phải thiết kế logging dành cho bộ biến đổi bao phủ toàn bộ JDK.

### Mã ứng dụng và hai lớp thử nghiệm

Tệp `src/app/demo/app/Main.java`:

```java
package demo.app;

import demo.agent.LifecycleAgent;

public final class Main {
    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("app: before Target");
        Class.forName("demo.app.Target");

        System.out.println("app: remove second=" + LifecycleAgent.stopSecond());
        System.out.println("app: remove second again=" + LifecycleAgent.stopSecond());

        System.out.println("app: before OtherTarget");
        Class.forName("demo.app.OtherTarget");
    }
}

final class Target {
    static {
        System.out.println("Target: initialized");
    }
}

final class OtherTarget {
    static {
        System.out.println("OtherTarget: initialized");
    }
}
```

`Target` và `OtherTarget` là hai lớp không công khai cùng package, đặt trong tệp `Main.java`. `Class.forName` dùng tên dạng chấm để yêu cầu nạp và khởi tạo từng lớp sau các mốc in ra; trong callback, tên tương ứng có dạng dấu `/`.

Ứng dụng nhập `LifecycleAgent` để điều khiển phép thử. Sự phụ thuộc này là lựa chọn minh họa vòng đời, không phải yêu cầu rằng mọi ứng dụng dùng agent đều phải nhập mã agent.

### Manifest

Tệp `agent-manifest.mf`, lưu không có BOM và có xuống dòng ở cuối:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.LifecycleAgent

```

Ví dụ chỉ đăng ký với `false`, không gọi retransformation, nên không yêu cầu khả năng retransformation trong manifest.

### Biên dịch và khởi chạy

Từ thư mục chứa `src` và manifest, dùng JDK 17 trở lên:

```shell
javac --release 17 -d out/agent src/agent/demo/agent/LifecycleAgent.java
javac --release 17 -cp out/agent -d out/app src/app/demo/app/Main.java
jar --create --file lifecycle-agent.jar --manifest agent-manifest.mf -C out/agent .
java "-javaagent:lifecycle-agent.jar" -cp out/app demo.app.Main
```

`-cp out/agent` ở bước biên dịch ứng dụng giúp `javac` tìm thấy lớp agent mà ứng dụng nhập. Khi chạy, agent JAR được cơ chế agent đưa vào phạm vi của system class loader; ví dụ không chép các lớp agent vào thư mục ứng dụng.

Stdout:

```text
agent: registered first, second
app: before Target
first: error on demo/app/Target
second: saw demo/app/Target
Target: initialized
app: remove second=true
app: remove second again=false
app: before OtherTarget
first: saw demo/app/OtherTarget
OtherTarget: initialized
```

Kết quả cho thấy:

1. Ngoại lệ giả lập trong `first` không ngăn `second` nhận `Target`.
2. `Target` vẫn khởi tạo vì không bộ nào cung cấp bytecode thay thế sai trong ví dụ.
3. Gỡ lần đầu thành công; lần sau không còn đăng ký tương ứng.
4. Khi nạp `OtherTarget` sau các lần gỡ trong phép thử một luồng này, chỉ `first` ghi nhận nó.

Không dùng kết quả một luồng để suy ra rằng môi trường nhiều luồng không thể có callback đang chạy sau khi gỡ. Ví dụ cũng không chứng minh hoàn tác bytecode, vì cả hai bộ đều không thay bytecode.

## 7. Các nguyên tắc khi đưa vào công cụ thực tế

**Khởi tạo trước, đăng ký sau.** Chuẩn bị cấu hình bất biến, bộ lọc và các phụ thuộc cần thiết trước `addTransformer`. Khi đăng ký xong, JVM có thể gọi bộ biến đổi trong quá trình nạp lớp đồng thời; không để callback đọc một cấu hình còn đang dựng dở.

**Lọc trước khi làm việc tốn kém.** Hạn chế phạm vi lớp theo nhu cầu. Không gọi `Class.forName(className...)` chỉ để tìm thông tin về chính lớp đang biến đổi: nó có thể gây vòng nạp lớp hoặc lỗi liên kết. Dữ liệu bytecode và các tham số đã cung cấp thường là điểm bắt đầu phù hợp.

**Không dựa riêng vào tên lớp để định danh toàn hệ thống.** Hai bộ nạp khác nhau có thể định nghĩa hai lớp cùng tên. Khi lưu trạng thái hoặc báo lỗi, cân nhắc ngữ cảnh bộ nạp, module và loại thao tác để tránh nhầm hai lớp thành một.

**Tách gỡ đăng ký khỏi giải phóng tài nguyên.** Cờ hoạt động giúp dừng công việc mới theo thiết kế; tài nguyên dùng chung phải còn sống đủ lâu cho công việc đang chạy. Đừng chỉ thêm khóa bao quanh mọi thao tác rồi giả định vấn đề đồng thời đã được giải quyết.

**Theo dõi lỗi mà không tạo vòng lỗi mới.** Bộ đếm, thông điệp ngắn và giới hạn tần suất thường hữu ích hơn việc in toàn bộ stack trace cho mọi lớp. Khi phép đo bị bỏ qua, phản ánh trạng thái đó cho người vận hành.

## 8. Tự kiểm chứng

- Đổi `first` từ ném lỗi sang trả về `null`; dự đoán những dòng nào thay đổi.
- Không gọi `stopSecond` trước `OtherTarget`; xác nhận cả hai bộ đều ghi nhận lớp đó.
- Giải thích vì sao `removeTransformer` trả `true` không đồng nghĩa bytecode cũ đã được khôi phục.
- Xét tình huống callback đọc cờ `true`, sau đó luồng điều khiển đặt `false`: công việc nào vẫn có thể tiếp tục?
- Phân biệt ba loại sự cố: lỗi đăng ký, ngoại lệ trong callback và trả về bytecode không hợp lệ. Mỗi loại cần quan sát và xử lý ở một vị trí khác nhau.
