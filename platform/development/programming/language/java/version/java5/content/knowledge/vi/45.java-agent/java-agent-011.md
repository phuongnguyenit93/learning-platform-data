# getObjectSize và ý nghĩa kích thước ước lượng

`Instrumentation.getObjectSize(Object)` giúp agent hỏi JVM về lượng bộ nhớ ước lượng của **một đối tượng cụ thể**. Giá trị trả về hữu ích khi khảo sát cách bố trí đối tượng, nhưng không tự trả lời “toàn bộ cấu trúc dữ liệu này chiếm bao nhiêu bộ nhớ?” hoặc “xóa biến này sẽ giải phóng bao nhiêu?”.

Muốn đọc đúng kết quả, trước hết phải xác định đang đo **bản thân đối tượng**, **đồ thị đối tượng được tham chiếu**, hay **bộ nhớ được đối tượng giữ sống**.

## 1. Hợp đồng API nói gì?

Chữ ký:

```java
long getObjectSize(Object objectToSize)
```

Đây là phương thức trên đối tượng `Instrumentation` do JVM cung cấp cho agent.

API trả về giá trị ước lượng phụ thuộc cách triển khai JVM. Kết quả có thể tính một phần hoặc toàn bộ chi phí phụ của đối tượng. Nó phù hợp hơn cho so sánh trong cùng một cách triển khai, không phải một định luật để so trực tiếp mọi JVM. Đặc tả còn cho phép ước lượng thay đổi trong cùng một lần chạy JVM.

Truyền `null` gây `NullPointerException`; không nhận kết quả `0`. Xem [hợp đồng getObjectSize](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object)) và [GetObjectSize trong JVM TI](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html#GetObjectSize).

Không cần biến đổi bytecode hay khai báo khả năng redefine để thực hiện thí nghiệm đo này.

## 2. Ba câu hỏi bộ nhớ khác nhau

| Câu hỏi | Khái niệm phù hợp |
| --- | --- |
| Một đối tượng riêng lẻ chiếm khoảng bao nhiêu? | Kích thước riêng, thường gọi là shallow size |
| Tập đối tượng đi tới được từ một điểm bắt đầu chiếm bao nhiêu? | Kích thước đồ thị, thường gọi là deep/graph size, với phạm vi được định nghĩa rõ |
| Những đối tượng nào mất khả năng được truy cập khi bỏ một đối tượng/tập giữ sống? | Retained size |

Ví dụ:

```text
holder ──value──> byte[1_000_000]
```

Bản thân `holder` chỉ có một ô tham chiếu `value`. Mảng là một đối tượng khác. Đo `holder` không phải phép cộng tự động cả mảng.

Tương tự, một mảng `Object[]` chứa các ô tham chiếu; các đối tượng được những ô đó trỏ tới không phải dữ liệu nằm trực tiếp bên trong từng ô. Ngược lại, phần tử của `byte[]` là dữ liệu nguyên thủy nằm trong chính mảng.

Điểm khác biệt shallow/retained được giải thích trong [tài liệu Eclipse Memory Analyzer](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/shallowretainedheap.html). Phần thí nghiệm sau tập trung vào phép đo từng đối tượng, rồi tự xác định một đồ thị nhỏ đã biết rõ.

## 3. Ví dụ hoàn chỉnh bằng Java agent

Ví dụ chạy với JDK 17+, dùng agent khởi động cùng JVM để giữ tham chiếu `Instrumentation`.

### 3.1. Cấu trúc tệp

```text
size-demo/
├── agent.mf
└── src/
    └── demo/
        ├── agent/
        │   └── SizeAgent.java
        └── app/
            └── Main.java
```

### 3.2. Agent cung cấp phép đo

Tệp `src/demo/agent/SizeAgent.java`:

```java
package demo.agent;

import java.lang.instrument.Instrumentation;

public final class SizeAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
    }

    public static long sizeOf(Object object) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        return inst.getObjectSize(object);
    }
}
```

`sizeOf` là phương thức phụ trợ của ví dụ. Phép đo thật nằm ở lời gọi `inst.getObjectSize(object)`.

Nếu không khởi động agent, mã báo thiếu `-javaagent` thay vì dùng một giá trị mặc định làm người đọc hiểu nhầm đã đo thành công.

### 3.3. Ứng dụng tạo các trường hợp đối chứng

Tệp `src/demo/app/Main.java`:

```java
package demo.app;

import demo.agent.SizeAgent;

public class Main {
    private static final class Holder {
        Object value;
    }

    public static void main(String[] args) {
        Object shared = new Object();
        Holder holder = new Holder();
        long holderBefore = SizeAgent.sizeOf(holder);
        holder.value = new byte[1_000_000];
        long holderAfter = SizeAgent.sizeOf(holder);
        Object[] refs = {shared, shared, shared};

        System.out.println("object=" + SizeAgent.sizeOf(shared));
        System.out.println("byte[0]=" + SizeAgent.sizeOf(new byte[0]));
        System.out.println("byte[1]=" + SizeAgent.sizeOf(new byte[1]));
        System.out.println("byte[8]=" + SizeAgent.sizeOf(new byte[8]));
        System.out.println("byte[9]=" + SizeAgent.sizeOf(new byte[9]));
        System.out.println("holder.before=" + holderBefore);
        System.out.println("holder.after=" + holderAfter);
        System.out.println("payload=" + SizeAgent.sizeOf(holder.value));
        System.out.println("refs=" + SizeAgent.sizeOf(refs));
        System.out.println("shared=" + SizeAgent.sizeOf(shared));
        try {
            SizeAgent.sizeOf(null);
        } catch (NullPointerException e) {
            System.out.println("null=NullPointerException");
        }
    }
}
```

`Holder` là lớp lồng `static`, vì vậy thí nghiệm không vô tình thêm tham chiếu tới một đối tượng bao ngoài. Biến `shared` được dùng lại trong cả ba ô của `refs`; chỉ có một đối tượng đích.

### 3.4. Manifest, biên dịch và chạy

Tệp `agent.mf`, có dòng trống cuối:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.SizeAgent

```

Lưu các tệp Java UTF-8 không BOM. Mở PowerShell tại `size-demo`, dùng JDK có `java`, `javac`, `jar` trong `PATH`:

```powershell
New-Item -ItemType Directory -Force out/agent, out/app, dist | Out-Null

javac --release 17 -d out/agent src/demo/agent/SizeAgent.java
javac --release 17 -cp out/agent -d out/app src/demo/app/Main.java
jar --create --file dist/size-agent.jar --manifest agent.mf -C out/agent .

java '-javaagent:dist/size-agent.jar' -cp 'out/app;dist/size-agent.jar' demo.app.Main
```

Chỉ tiếp tục khi từng lệnh thành công. Classpath dùng `;` trên Windows; đổi thành `:` nếu chạy trên Linux/macOS.

### 3.5. Kết quả đã đo

Một lượt chạy kiểm chứng dùng OpenJDK 24.0.2 Zulu, JVM 64 bit, `UseCompressedOops=true`, `UseCompressedClassPointers=true`, `ObjectAlignmentInBytes=8`. Mã được biên dịch với `--release 17`.

Stdout của lượt chạy đó:

```text
object=16
byte[0]=16
byte[1]=24
byte[8]=24
byte[9]=32
holder.before=16
holder.after=16
payload=1000016
refs=32
shared=16
null=NullPointerException
```

Đây là số đo của môi trường nêu trên. Nếu máy khác in số khác, hãy kiểm tra JVM và cấu hình trước khi kết luận ví dụ sai. Kích thước tham chiếu, phần đầu đối tượng và cách căn chỉnh không phải hằng số bắt buộc giống nhau trên mọi môi trường Java.

## 4. Giải thích số đo mà không suy diễn quá mức

### 4.1. Đối tượng rỗng vẫn có chi phí

`new Object()` không chứa trường do ứng dụng khai báo, nhưng số đo vẫn là `16` trong lượt chạy trên. “Không có trường” không đồng nghĩa “không chiếm bộ nhớ”.

Một mô hình giải thích thường dùng là:

```text
kích thước riêng ≈ căn_chỉnh(phần_đầu + dữ_liệu_trực_tiếp)
```

Mô hình này giúp tư duy, không thay cho việc khảo sát cách bố trí thực tế. Dự án [Java Object Layout của OpenJDK](https://github.com/openjdk/jol) cung cấp công cụ xem bố trí và footprint đối tượng, bao gồm thông tin tham chiếu và căn chỉnh của môi trường.

### 4.2. Mảng tăng theo bậc căn chỉnh

Trong kết quả:

```text
byte[1] = 24
byte[8] = 24
byte[9] = 32
```

Hai độ dài khác nhau có thể nhận cùng kích thước riêng. Khi thêm một phần tử vượt ranh giới căn chỉnh, tổng số đo mới tăng.

Chẳng hạn, mô hình có phần đầu mảng `16` byte và căn chỉnh `8` byte khớp các số đo này:

```text
alignUp(16 + 1, 8) = 24
alignUp(16 + 8, 8) = 24
alignUp(16 + 9, 8) = 32
```

Đây là mô hình diễn giải cho cấu hình đã đo; chỉ từ vài giá trị `getObjectSize` không nên tuyên bố đã chứng minh toàn bộ cấu trúc bên trong của JVM.

### 4.3. Đổi đối tượng được trỏ tới không làm ô tham chiếu lớn theo

`holder.before` và `holder.after` đều bằng `16`. Trước khi gán, trường `value` là `null`; sau khi gán, cùng ô tham chiếu trỏ tới một mảng lớn.

Phần dữ liệu của mảng được đo riêng bằng:

```java
SizeAgent.sizeOf(holder.value)
```

Trong lượt chạy, kết quả là `1_000_016`. Độ dài `1_000_000` là số phần tử `byte`; không nên gọi nhầm nó là một mebibyte (`1 MiB = 1_048_576` byte).

### 4.4. Ba tham chiếu không tạo ba bản sao đối tượng

Đồ thị của `refs`:

```text
refs[0] ─┐
refs[1] ─┼──> shared
refs[2] ─┘
```

Phép đo `refs` cho `32`; phép đo `shared` cho `16`. Nếu phạm vi cần tính là đúng mảng `refs` cộng các đối tượng mà phần tử trỏ tới, thì trong thí nghiệm này chỉ có hai đối tượng khác nhau:

```text
S(refs) + S(shared) = 32 + 16 = 48
```

Không cộng `shared` ba lần. Đây là tổng thủ công của đồ thị nhỏ đã biết, không phải việc `getObjectSize(refs)` tự trả deep size.

Với đồ thị bất kỳ, cần xử lý đối tượng dùng chung và chu trình bằng danh tính đối tượng, không dùng `equals()` để quyết định hai đối tượng có phải cùng một đối tượng hay không. Ngoài ra phải định nghĩa rõ những cạnh nào được duyệt; một phép duyệt phản chiếu tùy ý chưa đủ để trở thành công cụ đo heap chính xác.

## 5. Vì sao tổng đồ thị chưa phải retained size?

Giả sử `shared` còn được giữ bằng một tham chiếu mạnh khác từ gốc GC. Khi mảng `refs` mất khả năng được truy cập, `shared` vẫn sống. Vì vậy, bộ nhớ có thể thu hồi do bỏ `refs` không tự bao gồm `shared`, dù một phép tính đồ thị từ `refs` đã cộng nó.

Retained size phụ thuộc quan hệ giữ sống trong toàn đồ thị heap, không chỉ các đối tượng mà một điểm bắt đầu nhìn thấy. Xem [khái niệm retained heap của Eclipse MAT](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/shallowretainedheap.html).

Do đó, khi điều tra một bộ nhớ đệm lớn, ba câu có thể có ba đáp án:

- Bản thân đối tượng bộ nhớ đệm nhỏ đến mức nào?
- Các mục và dữ liệu truy cập được từ nó lớn đến mức nào?
- Nó đang giữ sống riêng bao nhiêu dữ liệu mà nơi khác không giữ?

`getObjectSize` trực tiếp giải quyết phép đo từng đối tượng; không tự trả lời toàn bộ ba câu.

## 6. Những cách diễn giải sai thường gặp

| Cách làm hoặc kết luận | Vấn đề |
| --- | --- |
| “Đo được 16 nên lớp này luôn chiếm 16 byte ở mọi JVM” | Biến kết quả phụ thuộc triển khai thành quy tắc ngôn ngữ |
| “Holder chỉ 16 byte nên không đáng kể trong bài toán bộ nhớ” | Bỏ qua đồ thị lớn mà nó có thể giữ |
| Cộng kích thước mọi phần tử mảng tham chiếu mà không khử trùng | Đếm lặp đối tượng dùng chung |
| Gọi `sizeOf(42)` rồi cho đó là kích thước kiểu `int` | Đối số được boxing thành đối tượng `Integer` |
| Đo `String` rồi coi đó là toàn bộ dữ liệu văn bản | Bỏ qua đối tượng lưu dữ liệu được tham chiếu |
| Đo đối tượng quản lý bộ nhớ native rồi coi đó là toàn bộ chi phí native | Trộn phạm vi đối tượng Java với bộ nhớ bên ngoài heap |
| Lấy heap dùng trước/sau một lệnh làm kích thước chính xác của một đối tượng | Kết quả có thể lẫn cấp phát khác, hoạt động GC và nhiễu môi trường |

Trường tĩnh cũng không phải một bản sao dữ liệu nằm trong từng đối tượng. Không tự cộng kích thước mọi trường khai báo bằng phản chiếu rồi gọi kết quả là kích thước riêng.

Tương tự, số byte của dữ liệu khi tuần tự hóa hoặc truyền qua mạng thuộc định dạng biểu diễn khác. Nó không được suy ra trực tiếp từ số đo đối tượng trong JVM.

## 7. Cách sử dụng kết quả có giá trị

Khi so sánh hai thiết kế dữ liệu, giữ cùng môi trường đo và ghi lại:

1. Phiên bản/vendor JVM, kiến trúc và các cấu hình bố trí liên quan.
2. Đối tượng đang đo là gì; với mảng phải ghi cả loại phần tử và độ dài.
3. Phạm vi kết quả: từng đối tượng, đồ thị đã xác định hay retained size.
4. Cách xử lý đối tượng dùng chung, nếu có phép cộng đồ thị.
5. Kết quả quan sát và giới hạn diễn giải.

Nếu cần xem bố trí trường và khoảng đệm, dùng thông tin bố trí phù hợp như JOL. Nếu cần tìm nguồn giữ sống và retained heap trong một ảnh chụp heap, dùng công cụ phân tích heap phù hợp. Đừng đổi tên một phép đo từng đối tượng thành số đo toàn bộ ứng dụng.

## 8. Tự thực hành

- Thay `byte[9]` bằng vài độ dài liên tiếp và tìm các bậc tăng trong cấu hình đang dùng.
- Giữ nguyên `Holder`, thay kích thước mảng nó trỏ tới: so sánh phép đo `holder` và `holder.value`.
- Thay ba phần tử của `refs` bằng ba `new Object()` khác nhau: tính lại đồ thị nhỏ theo danh tính đối tượng.
- Giải thích vì sao `sizeOf(null)`, `sizeOf(new byte[0])` và `sizeOf(new Object[0])` là ba tình huống khác nhau.

Cách đọc đúng là luôn gắn số đo với **đối tượng, phạm vi và môi trường**. Một số `long` từ `getObjectSize` là dữ liệu hữu ích để phân tích, không phải lời giải sẵn cho mọi câu hỏi về bộ nhớ.
