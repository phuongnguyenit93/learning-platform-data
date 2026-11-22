# Java agent ảnh hưởng thế nào đến hiệu năng, tính đúng và khả năng nạp lớp?

## 1. Agent chạy cùng JVM nên tác động nằm trong ứng dụng

Một Java agent thường được dùng để thu thập dữ liệu hoặc biến đổi mã mà không phải sửa từng tệp nguồn của ứng dụng. Tuy nhiên, agent chạy trong cùng JVM và có thể tham gia vào dữ liệu lớp trước khi JVM định nghĩa lớp.

Vì vậy, “không sửa mã nguồn” không có nghĩa “không làm thay đổi quá trình chạy”.

Cần đánh giá ba mặt riêng:

| Mặt cần đánh giá | Câu hỏi |
| --- | --- |
| Hiệu năng | Agent làm tăng thời gian, CPU, cấp phát, bộ nhớ hoặc cạnh tranh tài nguyên ở đâu? |
| Tính đúng | Kết quả, ngoại lệ, thứ tự tác dụng phụ và quy tắc đồng thời của ứng dụng có được giữ không? |
| Khả năng nạp lớp | Dữ liệu lớp sau biến đổi có hợp lệ và các lớp hỗ trợ có nạp/liên kết được không? |

Ba mặt này liên quan nhưng không thay thế nhau. Một agent có thể tạo số liệu chính xác nhưng quá tốn bộ nhớ; cũng có thể chạy nhanh trên đường thành công nhưng làm mất ngoại lệ gốc khi lỗi xảy ra.

Bài tập trung vào cơ chế Java Instrumentation vẫn dùng trên JDK hiện đại, với ví dụ JDK 17+. Không giả định mọi agent có cùng mức chi phí và không gán một tỷ lệ “overhead chuẩn” cho toàn bộ công cụ.

## 2. Chi phí xuất hiện ở những giai đoạn nào?

### 2.1. Khởi tạo agent

Agent khởi động bằng `-javaagent` có `premain` chạy trước `main` của ứng dụng. Các việc như đọc cấu hình, nạp thư viện xử lý bytecode, tạo luồng nền hoặc khởi tạo bộ xuất dữ liệu đều có thể làm tăng thời gian khởi động.

Nếu `premain` ném lỗi không được xử lý hoặc agent không thể khởi động đúng, JVM có thể dừng trước khi vào `main`. Đây là lỗi khởi động, không phải chỉ một lần thu thập số liệu bị thiếu.

Cần xác định thời điểm “ứng dụng đã sẵn sàng” theo mục tiêu thực tế. Đo từ dòng đầu `main` sẽ bỏ qua phần thời gian agent đã tiêu tốn trước đó.

### 2.2. Nạp, biến đổi và định nghĩa lớp

Khi có sự kiện phù hợp, transformer thực hiện công việc trên đường xử lý lớp:

```text
Đọc/tạo dữ liệu lớp
    ↓
Lọc lớp cần quan tâm
    ↓
Phân tích class file
    ↓
Tạo dữ liệu đã biến đổi
    ↓
JVM kiểm tra, định nghĩa và liên kết theo nhu cầu
```

Chi phí có thể gồm kiểm tra tên, phân tích bảng hằng, tìm phương thức, tính thông tin kiểm tra bytecode, tạo mảng mới, nạp các lớp hỗ trợ và xác minh kết quả.

Ngay cả transformer chỉ trả `null` cũng đã chạy một đoạn mã để quyết định không biến đổi. Tuy nhiên, điều đó không đồng nghĩa đoạn mã ấy được chạy lại ở mỗi lần gọi phương thức.

Một bộ lọc tên đơn giản có thể loại nhanh lớp ngoài phạm vi trước khi phân tích sâu. Trái lại, phân tích toàn bộ mọi lớp rồi mới quyết định bỏ qua sẽ làm công việc không cần thiết tăng lên.

### 2.3. Khi phương thức đã biến đổi được thực thi

Nếu agent chèn thêm mã vào thân phương thức, phần mã đó chạy cùng các lời gọi ứng dụng:

```text
Phương thức gốc:
    thực hiện nghiệp vụ

Sau khi chèn mã:
    ghi nhận bắt đầu
    thực hiện nghiệp vụ
    ghi nhận kết thúc hoặc lỗi
```

Đây là mô hình, không phải mã Java hoàn chỉnh.

Chi phí lúc thực thi phụ thuộc số lần phương thức được gọi và công việc được chèn: lấy thời gian, cấp phát sự kiện, tra ngữ cảnh, cập nhật bộ đếm, dùng khóa, xếp hàng hoặc gửi dữ liệu.

Có thể dùng mô hình suy nghĩ gần đúng:

```text
Chi phí thực thi bổ sung
    ≈ số lần ghi nhận × chi phí mỗi lần ghi nhận
      + chi phí cấp phát/GC/cạnh tranh tài nguyên liên quan
```

Đây không phải công thức dự báo chính xác. Khi có cạnh tranh khóa, hàng đợi đầy, áp lực GC hoặc thay đổi cách JIT tối ưu, chi phí có thể tăng không tuyến tính.

### 2.4. Bộ nhớ và vòng đời dài

Agent có thể giữ:

- Mảng byte và cấu trúc phân tích lớp.
- Cache theo lớp, bộ nạp lớp hoặc phương thức.
- Dữ liệu đo và hàng đợi sự kiện.
- Ngữ cảnh gắn với luồng.
- Luồng xuất dữ liệu, kết nối và bộ đệm.

Một cache giữ tham chiếu mạnh tới `Class` hoặc `ClassLoader` có thể kéo dài vòng đời của chúng và các tài nguyên liên quan. Điều này đặc biệt đáng kiểm tra ở môi trường nạp/gỡ ứng dụng hoặc plugin nhiều lần.

Chỉ xem heap tăng ngay sau khởi động chưa đủ để kết luận rò rỉ. Cần quan sát sau các chu kỳ hoạt động và vòng đời có ý nghĩa, đồng thời phân biệt cache có giới hạn với dữ liệu tăng không có điểm dừng.

### 2.5. Biến đổi lại lớp đang chạy

Khi dùng `retransformClasses` hoặc `redefineClasses`, công việc xử lý không chỉ xảy ra lúc khởi động. Việc thay mã có thể phát sinh chi phí xử lý dữ liệu lớp và ảnh hưởng tới quá trình tối ưu mã của JVM.

Không nên kết luận tác động chỉ bằng cách đo trạng thái ổn định rất lâu sau khi thay mã. Nếu hệ thống thực sự thay nhiều lớp trong lúc có tải, cần đo cả khoảng thời gian thao tác đó diễn ra.

## 3. Giữ tính đúng không chỉ là giữ cùng một giá trị trả về

### 3.1. Ngoại lệ không được bị che khuất

Xét đoạn mã minh họa:

```java
try {
    return performBusiness();
} finally {
    reportTelemetry();
}
```

Đây là đoạn mô tả ý tưởng chèn mã, không phải một chương trình độc lập.

Nếu `reportTelemetry()` ném ngoại lệ, nó có thể thay thế kết quả trả về hoặc ngoại lệ gốc của `performBusiness()`. Vậy một lỗi ghi số liệu có thể làm ứng dụng thất bại theo cách mới.

Công cụ cần quy định rõ cách xử lý lỗi của phần quan sát: lỗi nào được ghi nhận, có thể bỏ sự kiện hay không, và trường hợp nào cần báo động. Không giải quyết bằng một câu “bắt mọi thứ rồi bỏ qua”: che lỗi lập trình hoặc lỗi nghiêm trọng cũng có thể làm dữ liệu sai mà không ai biết.

### 3.2. Thêm mã không được vô tình gọi thêm nghiệp vụ

Ghi nhận đối số bằng cách gọi `toString()` có thể chạy mã do ứng dụng định nghĩa. Mã đó có thể tốn thời gian, nạp lớp, truy cập dữ liệu, thay trạng thái hoặc ném ngoại lệ.

Tương tự, một getter dùng để “chỉ đọc thông tin” có thể thực hiện nhiều công việc hơn dự đoán. Phải xem phần mã được chèn sẽ gọi gì, không chỉ xem nó cuối cùng ghi ra một chuỗi.

### 3.3. Thứ tự và đồng thời

Thêm khóa, cập nhật cấu trúc dùng chung hoặc thao tác I/O trong đường xử lý nóng có thể làm tăng chờ đợi. Nếu agent và ứng dụng lấy khóa theo thứ tự khác nhau, có thể tạo bế tắc.

Việc ghi nhận không được dựa trên giả định chỉ có một luồng gọi transformer hoặc một luồng chạy phương thức đích. Trạng thái dùng chung cần tuân theo quy tắc đồng thời phù hợp.

Một agent cũng có thể làm thay đổi thời điểm các luồng chạy. Nếu một lỗi tranh chấp biến mất sau khi bật agent, đó không phải bằng chứng mã ứng dụng đã đúng; lịch chạy có thể đã thay đổi.

### 3.4. Đường trả về sớm, đệ quy và lỗi

Muốn đếm thời gian xử lý, cần xác định rõ có tính:

- Những lần ném ngoại lệ.
- Các lệnh `return` sớm.
- Lời gọi đệ quy.
- Các lời gọi lồng nhau.
- Thời gian chờ hay chỉ thời gian CPU.
- Công việc được chuyển sang luồng khác.

Một phép đo có thể được cài đúng về bytecode nhưng sai về ý nghĩa. Ví dụ, đo thời gian của hàm gửi tác vụ vào hàng đợi không tự cho thời gian hoàn tất tác vụ bất đồng bộ.

### 3.5. Trạng thái đã có sau khi thay mã

Định nghĩa lại/biến đổi lại không tự chạy lại mọi constructor hoặc khởi tạo lại trạng thái tĩnh. Mã mới cần tương thích với các đối tượng cũ.

Một phương thức đang thực thi có thể tiếp tục dùng bytecode cũ, còn lời gọi mới dùng bản mới. Không coi việc thay mã thành công là một thao tác tự di chuyển toàn bộ trạng thái nghiệp vụ.

## 4. Vì sao một agent có thể làm lớp không nạp được?

### 4.1. Dữ liệu class file không hợp lệ

Transformer phải trả một class file hoàn chỉnh, hợp lệ. Những lỗi có thể gặp gồm:

- Mảng rỗng hoặc thiếu dữ liệu.
- Sai định dạng bảng hằng.
- Mã JVM không khớp kiểu/ngăn xếp.
- Thông tin kiểm tra không phù hợp.
- Tên lớp không khớp lớp cần định nghĩa.
- Phiên bản class file không được JVM hiện tại hỗ trợ.

Tùy lỗi và giai đoạn kiểm tra, có thể xuất hiện `ClassFormatError`, `VerifyError`, `NoClassDefFoundError`, `UnsupportedClassVersionError` hoặc một lỗi liên kết khác. Không dùng một kiểu ngoại lệ duy nhất để mô tả mọi lỗi biến đổi.

Khi có nhiều transformer, JVM xét dữ liệu sau chuỗi biến đổi. Callback của một công cụ chạy thành công không chứng minh đầu ra cuối cùng sẽ được JVM chấp nhận.

### 4.2. Lớp hỗ trợ không nhìn thấy được từ lớp đích

Giả sử agent chèn một lời gọi tới `helper.Probe.record()`. Lớp agent nhìn thấy `Probe` chưa đủ; mã đích phải liên kết được tới nó trong ngữ cảnh bộ nạp/module của lớp đích.

Một ứng dụng classpath đơn giản có thể chạy tốt nhưng môi trường plugin với bộ nạp riêng lại lỗi. Cùng tên lớp nhưng được định nghĩa bởi hai bộ nạp khác nhau cũng không mặc nhiên là cùng kiểu.

Với lớp do bộ nạp bootstrap định nghĩa, việc hỗ trợ phải được thiết kế riêng. Lớp hỗ trợ đặt vào đường tìm kiếm bootstrap chỉ nên liên kết tới các lớp mà bộ nạp đó có thể định nghĩa; không giả định nó nhìn thấy mọi thư viện ứng dụng.

### 4.3. Quy tắc module và truy cập

JDK hiện đại có module. Khả năng nhìn thấy lớp, khả năng truy cập thành viên và quyền phản chiếu sâu là những vấn đề khác nhau.

JVM có hỗ trợ riêng cho instrumentation: module của lớp đã biến đổi được bố trí đọc unnamed module của bộ nạp bootstrap và bộ nạp lớp agent. Hỗ trợ đó không đồng nghĩa mọi thành viên private hoặc mọi package trong mọi named module đều mở cho mọi loại truy cập.

Khi thêm mã hỗ trợ hoặc dùng reflection, cần kiểm tra đúng quan hệ đọc, xuất package và mở package theo kiểu truy cập đang dùng. Không thêm hàng loạt tùy chọn mở module chỉ để che một lỗi chưa được chẩn đoán.

### 4.4. Vòng lặp nạp lớp và khởi tạo phụ thuộc

Transformer có thể cần logger, thư viện bytecode hoặc lớp hỗ trợ để xử lý dữ liệu. Việc dùng chúng lại có thể yêu cầu nạp thêm lớp, dẫn đến callback khác.

Nếu trong lúc biến đổi lớp C, agent chủ động nạp hoặc liên kết chính C, có thể gây vòng lặp hoặc lỗi liên kết. Biến đổi các lớp JDK mà chính agent đang phụ thuộc càng cần thận trọng.

Lỗi liên kết do quá trình này có thể ảnh hưởng các lần phân giải tham chiếu về sau; không giả định thử nạp lại ngay sẽ luôn xóa được trạng thái lỗi.

Hướng thiết kế thường là giảm phụ thuộc trong callback, chuẩn bị những thành phần cần thiết trước khi đăng ký và loại trừ mã nội bộ của agent khi phù hợp. Việc chuẩn bị trước giúp giảm rủi ro nhưng không chứng minh mọi vòng phụ thuộc đã được loại bỏ.

### 4.5. Khóa khi nạp lớp

Callback diễn ra trên đường xử lý lớp. Nếu nó chờ mạng, tệp hoặc khóa ứng dụng, luồng đang cần lớp đó cũng bị chậm theo.

Một số quá trình nạp lớp giữ khóa liên quan bộ nạp. Nếu agent lấy thêm một khóa mà luồng khác đang giữ trong lúc luồng đó lại chờ nạp lớp, có thể xuất hiện chu trình chờ. Vì vậy, không nên xem callback như nơi thích hợp để thực hiện công việc tùy ý có thể chặn lâu.

## 5. Thí nghiệm: callback nạp lớp và lỗi dữ liệu lớp

Ví dụ dùng hai chế độ:

- `observe`: đếm số lần callback nhận đúng lớp đích rồi trả `null`.
- `broken`: cố ý trả dữ liệu không phải class file hợp lệ để nhìn thấy JVM từ chối.

Chế độ `broken` chỉ dùng để minh họa lỗi trong thư mục thực hành. Nó không phải cách xử lý lỗi hay cách chặn lớp nên áp dụng cho công cụ thật.

### 5.1. Tệp src/demo/ImpactAgent.java

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicInteger;

public final class ImpactAgent {
    public static void premain(String args, Instrumentation instrumentation) {
        String mode = args == null ? "observe" : args;
        if (!"observe".equals(mode) && !"broken".equals(mode)) {
            throw new IllegalArgumentException("Expected observe or broken");
        }
        AtomicInteger matched = new AtomicInteger();
        Runtime.getRuntime().addShutdownHook(new Thread(() ->
                System.out.println("[agent] target callbacks=" + matched.get()),
                "agent-summary"));

        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> classBeingRedefined, ProtectionDomain domain,
                    byte[] classfileBuffer) {
                if (!"demo/Work".equals(className)) {
                    return null;
                }
                matched.incrementAndGet();
                if ("broken".equals(mode)) {
                    return new byte[] {0, 0, 0, 0};
                }
                return null;
            }
        });
        System.out.println("[agent] mode=" + mode);
    }
}
```

Bộ đếm được tạo trước khi đăng ký transformer. Callback loại nhanh mọi tên khác `demo/Work`, không in log cho từng sự kiện. Dòng tổng kết được in ở shutdown hook khi chương trình của bài kết thúc bình thường.

`AtomicInteger` giúp phép tăng bộ đếm không bị mất cập nhật khi có nhiều luồng; lựa chọn bộ đếm của công cụ thực tế vẫn cần được đánh giá theo tải. Ví dụ không cache đối tượng `Class` hoặc bộ nạp lớp.

### 5.2. Tệp src/demo/Work.java

```java
package demo;

public final class Work {
    public static int compute(int value) {
        return value + 1;
    }
}
```

### 5.3. Tệp src/demo/App.java

```java
package demo;

import java.lang.reflect.Method;

public final class App {
    public static void main(String[] args) throws Exception {
        System.out.println("[app] start");
        try {
            Class<?> type = Class.forName("demo.Work");
            Method method = type.getMethod("compute", int.class);
            int sum = 0;
            for (int i = 0; i < 1000; i++) {
                sum += (Integer) method.invoke(null, 41);
            }
            System.out.println("[app] calls=1000 sum=" + sum);
        } catch (ClassFormatError expected) {
            System.out.println("[app] load=ClassFormatError");
        }
    }
}
```

Ứng dụng nạp lớp theo tên chuỗi sau dòng đầu tiên để quan sát được thời điểm rõ ràng. Vòng lặp dùng reflection nhằm không tham chiếu trực tiếp tới kiểu `Work` trong mã gọi.

**Đây là chương trình kiểm chứng hành vi, không phải benchmark.** Reflection và cách vòng lặp được viết đều không đại diện cho mọi ứng dụng thực tế.

### 5.4. Manifest và biên dịch

Tệp `MANIFEST.MF`:

```text
Manifest-Version: 1.0
Premain-Class: demo.ImpactAgent

```

Lưu dạng văn bản có ký tự xuống dòng kết thúc và một dòng trống cuối tệp.

Cấu trúc nguồn:

```text
src/demo/ImpactAgent.java
src/demo/Work.java
src/demo/App.java
MANIFEST.MF
```

Từ thư mục chứa nguồn và manifest, chạy bằng JDK 17+ trong PowerShell:

```powershell
javac --release 17 -d agent-classes src/demo/ImpactAgent.java
javac --release 17 -d app-classes src/demo/App.java src/demo/Work.java
jar --create --file impact-agent.jar --manifest MANIFEST.MF -C agent-classes .
```

Chỉ tiếp tục khi từng lệnh thành công. Agent JAR chỉ chứa mã agent; `Work.class` thuộc thư mục lớp của ứng dụng.

### 5.5. Chạy không có agent

```powershell
java -cp app-classes demo.App
```

Stdout:

```text
[app] start
[app] calls=1000 sum=42000
```

### 5.6. Chạy chế độ observe

```powershell
java "-javaagent:impact-agent.jar" -cp app-classes demo.App
```

Stdout:

```text
[agent] mode=observe
[app] start
[app] calls=1000 sum=42000
[agent] target callbacks=1
```

Một nghìn lần gọi `compute(41)` không làm transformer nhận lớp đích một nghìn lần. Trong cấu hình bài, lớp được nạp một lần, không có yêu cầu biến đổi lại, nên bộ đếm là 1.

Kết quả tổng vẫn đúng vì agent chỉ quan sát sự kiện lớp và trả `null`. Nó không chèn mã vào `compute`.

Nhưng không được kết luận chi phí agent bằng không: `premain`, đăng ký callback, bộ lọc, phép tăng bộ đếm, shutdown hook và tài nguyên liên quan vẫn đã tồn tại.

### 5.7. Chạy chế độ broken

```powershell
java "-javaagent:impact-agent.jar=broken" -cp app-classes demo.App
```

Stdout:

```text
[agent] mode=broken
[app] start
[app] load=ClassFormatError
[agent] target callbacks=1
```

JVM nhận mảng bốn byte không tạo thành class file hợp lệ nên từ chối định nghĩa lớp. Mã nguồn và tệp `Work.class` ban đầu vẫn đúng; lỗi xuất hiện do dữ liệu thay thế mà agent trả về.

Ứng dụng của bài chủ động bắt lỗi định dạng để in kết quả gọn. Điều này chỉ giúp quan sát thí nghiệm, không chứng minh hệ thống thực tế có thể tiếp tục phục vụ khi một lớp bắt buộc không nạp được.

Ba cách chạy đã được kiểm tra trên JDK 24.0.2 với dữ liệu lớp biên dịch `--release 17`. Những kết quả này chứng minh hành vi nạp và giá trị tính toán; chúng không cung cấp một tỷ lệ chi phí hiệu năng.

## 6. Đo ảnh hưởng hiệu năng như thế nào cho có ý nghĩa?

### Chọn đường cơ sở và chỉ thay một yếu tố

So sánh hai cấu hình có cùng JDK, tài nguyên CPU/bộ nhớ, dữ liệu đầu vào, tham số JVM và tải:

```text
A: ứng dụng không bật agent đang đánh giá
B: cùng ứng dụng, bật agent với cấu hình cần đánh giá
```

Nếu đồng thời đổi heap, phiên bản JDK và mức log, không thể quy toàn bộ khác biệt cho agent.

Cần kiểm tra agent thật sự được bật đúng trong JVM cần đo. Với công cụ tạo JVM con, không giả định tham số agent ở tiến trình cha tự được áp dụng đúng cho mọi tiến trình con.

### Tách các câu hỏi đo

| Mục tiêu | Dữ liệu cần quan sát |
| --- | --- |
| Khởi động | Thời gian từ khởi chạy tiến trình đến mức sẵn sàng đã định nghĩa |
| Trạng thái ổn định | Thông lượng, độ trễ, CPU sau giai đoạn làm nóng phù hợp |
| Cấp phát và bộ nhớ | Tốc độ cấp phát, GC, heap, bộ nhớ ngoài heap và cache liên quan |
| Đường xử lý chậm | Phân bố độ trễ, chẳng hạn p95/p99, không chỉ trung bình |
| Biến đổi khi có tải | Độ trễ/lỗi trong chính khoảng thời gian thay mã |
| Bộ xuất dữ liệu | Kích thước hàng đợi, số sự kiện mất, thời gian chờ và chi phí mạng |

Một công cụ giảm chi phí bằng cách bỏ rất nhiều sự kiện có thể tạo chỉ số hiệu năng đẹp hơn nhưng dữ liệu quan sát kém đầy đủ hơn. Phải báo cả chất lượng dữ liệu và tác động lên ứng dụng.

### Đo lặp, hiểu quá trình làm nóng

Một lần chạy có thể bị nhiễu bởi JIT, nạp lớp, GC, cache hoặc hoạt động khác của hệ điều hành. Nên có nhiều lần chạy độc lập và ghi rõ điều kiện.

Đo chi phí một thao tác nhỏ cần một thiết kế benchmark phù hợp. JMH của OpenJDK hỗ trợ benchmark trên JVM; vẫn phải bảo đảm tham số agent áp dụng cho đúng JVM thử nghiệm, tránh loại bỏ mã không dùng và tránh trộn phần thiết lập với phần cần đo.

Với một dịch vụ, benchmark vi mô không thay thế thử tải luồng xử lý thật. Việc đọc thời gian quanh một vòng lặp có in console cũng không tự tạo ra một phép đo đáng tin cậy.

`System.nanoTime()` có thể dùng để tính khoảng thời gian trong cùng JVM; nó không biến một kịch bản thiếu làm nóng và thiếu kiểm soát thành benchmark chính xác. Thời gian đo là thời gian trôi qua, không tự đồng nghĩa thời gian CPU.

### Tính tỷ lệ từ số đo có cùng ý nghĩa

Ví dụ công thức cho độ trễ của cùng một phép đo/điểm phân vị:

```text
Mức tăng độ trễ (%)
    = (độ_trễ_có_agent / độ_trễ_cơ_sở - 1) × 100

Mức giảm thông lượng (%)
    = (1 - thông_lượng_có_agent / thông_lượng_cơ_sở) × 100
```

Cần đường cơ sở khác 0 và các phép đo phải so sánh được. Không trộn trung bình của cấu hình A với p99 của cấu hình B. Không suy ra “agent tăng 5% ở mọi nơi” từ một kịch bản duy nhất.

Bài không đưa số phần trăm thực nghiệm vì chưa chạy một benchmark hiệu năng có thiết kế cho một hệ thống cụ thể.

## 7. Giảm tác động mà vẫn giữ dữ liệu hữu ích

### Chọn phạm vi trước khi làm việc nặng

Lọc tên lớp, bộ nạp và module khi phù hợp trước khi phân tích sâu. Tránh chọn toàn bộ JDK và toàn bộ thư viện nếu mục tiêu chỉ là một nhóm API của ứng dụng.

Không dùng duy nhất tiền tố tên lớp làm bằng chứng mọi lớp trùng tên trong mọi bộ nạp đều nên được biến đổi.

### Giữ đường nóng ngắn

Tránh I/O mạng đồng bộ và ghi console cho mọi lời gọi. Nếu xuất dữ liệu qua hàng đợi, hàng đợi phải có giới hạn và chính sách rõ khi đầy: bỏ sự kiện, giảm lấy mẫu hay tạo áp lực chờ đều có đánh đổi.

Xuất bất đồng bộ chỉ chuyển một phần công việc sang luồng khác; nó không xóa CPU, cấp phát và bộ nhớ cần dùng. Hàng đợi không giới hạn có thể đổi một vấn đề độ trễ thành một vấn đề bộ nhớ.

### Giảm sự kiện theo mục tiêu

Có thể dùng lấy mẫu hoặc tổng hợp bộ đếm khi phù hợp. Nhưng cần hiểu câu hỏi học tập/vận hành đang trả lời: lấy mẫu có thể không giữ được mọi lỗi hiếm hoặc mọi chuỗi lời gọi.

Đo trước khi quyết định tối ưu. Một phép tra cứu thêm trong đường gọi rất thường xuyên có thể đáng quan tâm hơn một công việc tương đối nặng chỉ xảy ra một lần lúc nạp lớp.

### Quản lý cache và ngữ cảnh

Đặt giới hạn dữ liệu, dọn ngữ cảnh khi kết thúc và thiết kế vòng đời gắn với bộ nạp/lớp một cách rõ ràng. Kiểm tra trường hợp tác vụ thất bại hoặc bị hủy, không chỉ đường kết thúc bình thường.

Đừng giữ mọi đối số/đối tượng của lời gọi trong một cache dài hạn chỉ vì có thể cần xem sau.

### Kiểm tra khi kết hợp nhiều agent

Các phép biến đổi được nối thành chuỗi; công cụ sau có thể nhận dữ liệu đã được công cụ trước sửa. Thứ tự còn chịu nhóm khả năng biến đổi lại, nên không chỉ nhìn thứ tự `-javaagent`.

Cần kiểm tra tổ hợp thật sẽ dùng: chỉ thử từng agent riêng rẽ chưa chứng minh chúng cùng giữ đúng hành vi và không biến đổi trùng một phương thức.

### Hiểu giới hạn của việc tắt agent

Gỡ một transformer chỉ ngăn các sự kiện tương lai theo hợp đồng, và vẫn có thể còn callback đang diễn ra. Việc đó không tự gỡ mã đã được chèn vào các lớp đã nạp.

Muốn có đường cơ sở sạch, một JVM mới không bật agent thường là ranh giới rõ ràng cho phép so sánh. Nếu công cụ có cơ chế tắt riêng, cần xác minh nó tắt phần nào: thu thập, xuất dữ liệu hay cả mã đã chèn.

## 8. Tình huống tự phân tích

1. Agent trả `null` với mọi lớp nhưng ứng dụng khởi động chậm hơn. Liệt kê công việc có thể phát sinh trước và trong callback; không kết luận phải có mã được chèn vào phương thức.
2. Chỉ đường ném ngoại lệ có lỗi sau khi bật agent. Kiểm tra logic ghi nhận trong nhánh kết thúc và khả năng che ngoại lệ gốc.
3. Agent chạy tốt trên classpath nhưng lỗi trong môi trường plugin. Kiểm tra danh tính lớp, bộ nạp và khả năng nhìn thấy lớp hỗ trợ.
4. CPU ổn định nhưng heap tăng khi gỡ/nạp plugin nhiều lần. Kiểm tra cache và các tham chiếu tới bộ nạp/lớp.
5. Độ trễ trung bình gần như không đổi nhưng p99 tăng. Xem khóa, GC, hàng đợi xuất dữ liệu và các thời điểm biến đổi lại.
6. Thay vòng lặp trong ví dụ thành 2.000 lần. Dự đoán tổng là 84.000 nhưng bộ đếm callback lớp đích vẫn là 1 trong cùng cấu hình. Giải thích vì sao đây vẫn chưa phải phép đo overhead.
7. Đổi chế độ `broken` thành ném một ngoại lệ từ callback. Đối chiếu hợp đồng `ClassFileTransformer`: ngoại lệ của callback không phải lệnh chắc chắn chặn lớp; không suy luận từ trường hợp trả byte hỏng sang trường hợp ném ngoại lệ.

Một agent đáng tin cậy cần được đánh giá ở cả ba mặt: **chi phí đo được, hành vi ứng dụng được giữ đúng và dữ liệu lớp/liên kết vẫn hợp lệ**. Chạy thành công một ví dụ nhỏ chỉ là bằng chứng cho đúng phạm vi ví dụ đó.

## Tài liệu đối chiếu

- [ClassFileTransformer trên JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): thời điểm callback, dữ liệu đầu ra và rủi ro vòng phụ thuộc nạp lớp.
- [Đặc tả java.lang.instrument](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): khởi động agent, bộ nạp và hỗ trợ module.
- [Instrumentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): thay mã, trạng thái và gỡ transformer.
- [ClassLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): mô hình nạp lớp và các liên kết từ lớp.
- [System.nanoTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html#nanoTime()): cách hiểu khoảng thời gian.
- [OpenJDK JMH](https://github.com/openjdk/jmh): công cụ hỗ trợ thiết kế benchmark trên JVM.
