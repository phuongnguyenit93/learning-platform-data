# JVM vận hành chương trình Java: bộ nạp lớp, bộ thực thi, bộ nhớ và bộ thu gom rác

Khi chạy `java Main`, JVM không chỉ “đọc file `.class` rồi chạy”. Nó phải **tìm và tạo biểu diễn của lớp**, **thực thi các lệnh bytecode**, **quản lý dữ liệu trong những vùng nhớ có vai trò khác nhau** và **thu hồi bộ nhớ heap không còn cần thiết**. Bốn phần này phối hợp trong suốt vòng đời chương trình.

Bài học tập trung vào vai trò, ranh giới trách nhiệm và quan hệ giữa **Class Loader**, **Execution Engine**, **Runtime Data Areas** và **Garbage Collector (GC)**. Các mô tả về Metaspace, JIT nhiều tầng và các cờ chẩn đoán sử dụng **HotSpot trên JDK 17+** làm ví dụ; một triển khai JVM khác có thể tổ chức nội bộ khác.

## 1. Bức tranh toàn cảnh

```text
Mã nguồn .java
    │ javac (trình biên dịch của JDK)
    ▼
Bytecode .class
    │
    ▼
[Class Loader] ── nạp / liên kết / khởi tạo lớp ──► [Thông tin lớp tại runtime]
    │                                                    │
    └──────────────────────┬─────────────────────────────┘
                           ▼
                  [Execution Engine]
                thông dịch / JIT bytecode
                           │
            đọc, tạo, cập nhật dữ liệu
                           ▼
                    [Bộ nhớ JVM]
             heap, stack, method area, PC...
                           ▲
                           │ theo dõi tham chiếu còn tới được
                    [Garbage Collector]
               thu hồi đối tượng heap không còn tới được
```

Sơ đồ là **mô hình khái niệm**, không hàm ý mọi mũi tên là một bước tuần tự hoặc GC chạy sau mỗi câu lệnh. Trong lúc JVM thực thi phương thức, nó có thể tiếp tục nạp lớp khác, cấp phát đối tượng mới, tối ưu mã đã chạy nhiều lần và thực hiện các pha GC.

| Thành phần | Câu hỏi nó giải quyết | Vai trò chính |
| --- | --- | --- |
| Class Loader | “Lớp này là lớp nào, mã và metadata của nó ở đâu?” | Tìm/nạp định nghĩa lớp, phối hợp liên kết và khởi tạo |
| Execution Engine | “Các lệnh trong phương thức được thực hiện thế nào?” | Chạy bytecode bằng thông dịch, biên dịch JIT và mã máy |
| Runtime Data Areas | “Dữ liệu và trạng thái thực thi nằm ở đâu?” | Cung cấp heap, stack và các vùng runtime khác |
| Garbage Collector | “Đối tượng heap nào không còn cần giữ?” | Xác định khả năng truy cập và thu hồi bộ nhớ tự động |

`javac` thuộc **JDK**; JVM là môi trường thực thi bytecode. **GC là một dịch vụ quản lý bộ nhớ bên trong JVM**, không phải trình nạp lớp hay bộ thực thi.

## 2. Class Loader: đưa định nghĩa lớp vào JVM

### 2.1. Tại sao phải nạp lớp?

Một file `.class` chứa bytecode, constant pool và mô tả trường, phương thức. JVM cần một biểu diễn runtime để xác định kiểu, tra cứu phương thức, kiểm tra truy cập và thực thi lệnh. Việc nạp lớp thường xảy ra **khi cần**, chứ không phải mọi class trên classpath đều được nạp khi chương trình khởi động.

Trong JVM, định danh của một lớp gắn với **tên nhị phân của lớp và defining class loader**. Hai class loader khác nhau định nghĩa cùng tên `com.example.Plugin` có thể tạo ra hai kiểu khác nhau; vì vậy ép kiểu hoặc giao tiếp qua plugin có thể gặp `ClassCastException` hoặc `LinkageError` dù tên lớp trông giống nhau.

### 2.2. Ba giai đoạn thường được nhắc đến

1. **Loading (nạp):** class loader tìm bytes của định nghĩa lớp và JVM tạo biểu diễn tương ứng.
2. **Linking (liên kết):** gồm **verification** (kiểm tra ràng buộc bytecode), **preparation** (cấp phát/đặt giá trị mặc định cho các trường `static`) và **resolution** (biến tham chiếu ký hiệu trong constant pool thành tham chiếu thực tế; có thể làm lười tùy JVM).
3. **Initialization (khởi tạo):** thực thi logic khởi tạo trường `static` và khối `static { ... }` theo quy tắc ngôn ngữ, thường do lần **sử dụng chủ động** đầu tiên kích hoạt.

Đừng đánh đồng **đã nạp** với **đã khởi tạo**. Ví dụ, việc lấy literal `SomeType.class` không nhất thiết chạy khối khởi tạo `static`. Ngược lại, đọc một trường `static` không phải hằng số biên dịch thường yêu cầu khởi tạo lớp khai báo trường đó. Việc tham chiếu một hằng số `static final` kiểu nguyên thủy/`String` có giá trị hằng số ngay lúc biên dịch có thể được inline và **không** kích hoạt khởi tạo lớp.

### 2.3. Các bộ nạp thông dụng trong HotSpot

| Loader | Trách nhiệm thường gặp |
| --- | --- |
| Bootstrap | Nạp các lớp nền tảng cốt lõi của Java; với `Class.getClassLoader()` có thể được biểu diễn là `null` |
| Platform | Nạp các lớp nền tảng do platform class loader phụ trách |
| Application/System | Nạp phần lớn lớp ứng dụng từ classpath/module path thích hợp |
| Custom | Nạp lớp theo nhu cầu riêng, chẳng hạn plugin, container hoặc cơ chế cô lập |

Các loader dựng sẵn thường dùng **parent delegation**: hỏi loader cha trước khi tự tìm định nghĩa. Cơ chế tùy biến có ngoại lệ; không được coi “cha luôn nạp trước” là luật áp dụng cho mọi custom loader.

**Nhiệm vụ của Class Loader kết thúc ở định nghĩa/chu kỳ lớp; nó không tự chạy toàn bộ thuật toán trong `main`.** Sau khi mã của phương thức được xác định, execution engine đảm nhận thực thi.

## 3. Execution Engine: thực hiện bytecode

Bytecode mô tả các thao tác như nạp biến, tính toán, gọi phương thức, tạo đối tượng, rẽ nhánh và trả về. Execution engine khiến những thao tác này có hiệu lực trong runtime.

- **Interpreter (trình thông dịch):** thực hiện bytecode khi chương trình chạy, cho phép phương thức được thực thi mà chưa cần có mã máy tối ưu hóa.
- **Just-in-Time compiler (JIT):** dựa trên thông tin thực thi (profiling), biên dịch các đoạn/phương thức thích hợp thành **mã máy native** để những lần chạy sau thường nhanh hơn. HotSpot có thể dùng tiered compilation, inlining và nhiều tối ưu hóa khác.
- **Deoptimization:** khi giả định dùng để tối ưu không còn đúng, HotSpot có thể quay về trạng thái thực thi ít tối ưu hơn để vẫn giữ nguyên ngữ nghĩa chương trình.

`JIT` không phải `javac`: `javac` biến mã nguồn thành bytecode **trước khi chạy**; JIT biên dịch bytecode thành mã máy **trong lúc chạy**. Không có cam kết rằng mọi phương thức đều được JIT, hay mọi lần gọi đều chạy đúng cùng một đường thực thi. Mã máy đã biên dịch có thể nằm trong **code cache** của HotSpot.

Ví dụ, với lời gọi `sum(2, 3)`, JVM tạo/ngắt một frame phương thức phù hợp, thực hiện các thao tác tính toán và đặt kết quả vào ngữ cảnh của bên gọi. Frame và dữ liệu dùng trong thao tác liên quan đến các vùng nhớ ở phần tiếp theo.

## 4. Runtime Data Areas: dữ liệu nằm ở đâu?

**Phân biệt quan trọng:** Java Virtual Machine Specification mô tả các vùng dữ liệu **theo chức năng**; tên và cách cấp phát thực tế ở HotSpot không luôn tương ứng 1–1 với cách vẽ trong tài liệu.

| Vùng nhớ | Chia sẻ hay riêng? | Chứa gì và dùng để làm gì? |
| --- | --- | --- |
| **Heap** | Chung cho các thread | Đối tượng và mảng được cấp phát tại runtime; vùng được GC quản lý chủ yếu |
| **Java Virtual Machine Stack** | Mỗi thread một stack | Các **frame** cho lời gọi phương thức Java: biến cục bộ, operand stack, thông tin liên kết/trở về |
| **PC Register** | Mỗi thread | Vị trí lệnh JVM đang thực thi trong phương thức Java hiện hành; nội dung với native method được quy định khác |
| **Method Area** | Chung | Mô tả lớp/kiểu, cấu trúc phương thức, runtime constant pool và dữ liệu mức lớp theo mô hình đặc tả |
| **Native Method Stack** | Gắn với thực thi native, tùy triển khai | Trạng thái hỗ trợ các phương thức native khi JVM sử dụng loại stack này |

Trong **HotSpot hiện đại**, phần lớn class metadata được lưu ở vùng native memory gọi là **Metaspace** (một cách hiện thực hóa phần thông tin của method area); **code cache** chứa mã máy đã biên dịch. Vì vậy **method area không đồng nghĩa giản đơn với “heap”**, và `-Xmx` không phải giới hạn tổng bộ nhớ của tiến trình.

### 4.1. Stack frame không phải heap object

Mỗi lần gọi phương thức Java tạo một ngữ cảnh frame với tham số, biến cục bộ và vùng tính toán toán hạng. Lời gọi kết thúc thì frame không còn hoạt động. Khi hàm chứa biến `Person p`, giá trị biến đó có thể là **tham chiếu đến đối tượng**, còn đối tượng thuộc mô hình **heap**, không phải “toàn bộ đối tượng nằm trong stack”.

Đây là mô hình lập trình/đặc tả. JIT có thể đặt giá trị ở thanh ghi hoặc loại bỏ cấp phát đối tượng nhờ escape analysis và scalar replacement; không nên suy luận vị trí vật lý chính xác từ một dòng mã nguồn.

### 4.2. Phạm vi sống của stack và heap khác nhau

Một biến cục bộ hết phạm vi không đồng nghĩa GC đã chạy. Khi **không còn đường tham chiếu mạnh nào từ GC roots tới đối tượng**, đối tượng có thể được thu hồi trong một đợt GC sau đó. Nếu đối tượng vẫn được lưu trong trường `static`, collection, thread-local hoặc đối tượng sống lâu khác, nó có thể tiếp tục được giữ dù phương thức tạo nó đã kết thúc.

### 4.3. Bộ nhớ ngoài heap cần phân biệt

Direct buffers, native allocations, metadata và thread stacks có thể dùng native memory. Garbage Collector của Java không thay thế nghĩa vụ đóng **file, socket, database connection** hoặc giải phóng các tài nguyên có vòng đời tường minh. Ưu tiên `try-with-resources` cho tài nguyên triển khai `AutoCloseable`.

## 5. Garbage Collector: thu hồi những đối tượng không còn tới được

GC tự động quản lý phần lớn vòng đời **bộ nhớ heap**. Ý tưởng cốt lõi là **reachability (khả năng truy cập)**, không phải “biến bị gán `null` thì lập tức xóa đối tượng”.

### 5.1. GC roots và đồ thị tham chiếu

GC bắt đầu từ các **roots** thích hợp với trạng thái runtime (ví dụ tham chiếu đang hoạt động trong thread, các tham chiếu mức lớp, JNI handles), lần theo quan hệ tham chiếu tới đối tượng có thể truy cập. Đối tượng không còn đường tới từ roots có thể bị thu hồi. Hai đối tượng chỉ trỏ qua lại với nhau nhưng không nối tới roots **vẫn có thể được thu hồi**.

```text
GC root ──► A ──► B           C ◄──► D
             │
             └────► E

A, B, E: còn tới được từ root.
C, D: chỉ trỏ cho nhau, không tới được từ root → có thể thu hồi.
```

Thuật toán và thời điểm cụ thể phụ thuộc collector: có thể đánh dấu, sao chép, di chuyển/compact, hoặc làm việc đồng thời với application threads. Một số hoạt động cần **safepoint/stop-the-world pause**; không nên khẳng định “GC chạy hoàn toàn nền” hoặc “GC luôn dừng toàn bộ ứng dụng như nhau”.

### 5.2. GC có thể và không thể bảo đảm điều gì?

- **Có:** tìm và xử lý các đối tượng không còn tới được theo chính sách collector, giúp tái sử dụng heap; các collector hiện đại cũng có thể phục vụ class unloading khi điều kiện phù hợp.
- **Không:** bảo đảm một đối tượng cụ thể được thu hồi ngay sau `obj = null`, bảo đảm độ trễ bằng 0, hoặc tự đóng mọi tài nguyên hệ điều hành.
- **`System.gc()`:** về cơ bản là một yêu cầu/gợi ý với runtime; có thể bị bỏ qua hoặc xử lý khác tùy cờ và triển khai, không phải phép xác nhận đối tượng đã được thu hồi.
- **Bộ nhớ rò rỉ trong Java:** vẫn có thể xảy ra theo nghĩa đối tượng **còn reachable nhưng không còn hữu ích** (ví dụ cache không giới hạn, listener không gỡ đăng ký).

Các collector như G1, ZGC hoặc Parallel GC tối ưu các mục tiêu throughput, pause và footprint khác nhau. Không có một thuật toán GC duy nhất được JVM Specification bắt buộc cho mọi JVM.

## 6. Lần theo một ví dụ Java 17 có thể chạy

Tạo file **`JvmFlowDemo.java`**:

```java
public class JvmFlowDemo {

    static class Config {
        static {
            System.out.println("Config initialized");
        }

        static int factor = 7; // Không phải hằng số compile-time.
    }

    static int twice(int number) {
        int result = number * 2;
        return result;
    }

    public static void main(String[] args) {
        System.out.println("main begins");

        int output = twice(Config.factor);
        System.out.println("result = " + output);

        Object sample = new Object();
        System.out.println("object type: " + sample.getClass().getSimpleName());
        sample = null; // Không chứng minh GC sẽ chạy ngay.

        System.out.println("main ends");
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac JvmFlowDemo.java
java JvmFlowDemo
```

**Stdout của chương trình:**

```text
main begins
Config initialized
result = 14
object type: Object
main ends
```

Diễn giải từng điểm:

1. `javac` tạo `JvmFlowDemo.class` và `JvmFlowDemo$Config.class` từ mã nguồn (tên file class lồng là quy ước biên dịch của `javac`).
2. Khi khởi động, JVM nạp/liên kết/khởi tạo những lớp cần thiết để chạy `main`. Việc tải các lớp phụ thuộc khác có thể tiếp diễn sau đó.
3. Lệnh đầu của `main` in `main begins`. Biểu thức đọc trường `Config.factor` kích hoạt khởi tạo `Config` nếu chưa khởi tạo, vì đây là **trường `static` không phải hằng số compile-time**. Do đó dòng `Config initialized` xuất hiện trước `result = 14`.
4. Lời gọi `twice` cần ngữ cảnh thực thi của phương thức: tham số `number`, biến cục bộ `result`, phép nhân và giá trị trả về. Interpreter hoặc mã do JIT sinh ra thực hiện các thao tác với cùng kết quả quan sát được.
5. `new Object()` tạo đối tượng theo ngữ nghĩa Java; biến `sample` giữ tham chiếu đến nó. JVM thực thi `getClass().getSimpleName()` và in `Object`.
6. Sau khi gán `sample = null`, chương trình không còn cố ý giữ tham chiếu qua biến này; nếu không còn đường tham chiếu mạnh khác thì đối tượng **có thể đủ điều kiện** để GC thu hồi. Ví dụ **không hề chứng minh thời điểm GC**, và output không phụ thuộc vào việc GC chạy.

> Lưu ý: JVM/JIT được phép tối ưu hóa việc sử dụng và cấp phát đối tượng nếu giữ đúng hành vi quan sát được. Mô tả “đối tượng trên heap, tham chiếu trong frame” là mô hình học hữu ích, không phải bản đồ chính xác của từng ô nhớ sau tối ưu hóa.

## 7. Phối hợp bốn thành phần trong vòng đời ứng dụng

| Sự kiện | Class Loader | Execution Engine | Runtime Data Areas | GC |
| --- | --- | --- | --- | --- |
| JVM chuẩn bị gọi `main` | Nạp/liên kết các lớp cần thiết | Chuẩn bị thực thi bytecode | Metadata lớp, trạng thái thread/frame | Chưa nhất thiết có hoạt động nào |
| Chạm tới một lớp mới | Nạp/liên kết, khởi tạo khi điều kiện kích hoạt | Thực thi mã khởi tạo nếu cần | Cập nhật dữ liệu mức lớp | Có thể hoạt động độc lập |
| Gọi phương thức | Có thể cần nạp thêm kiểu phụ thuộc | Thông dịch/JIT, thực hiện lệnh | Frame, PC, đối tượng được truy cập | Có thể chạy xen kẽ với ứng dụng |
| Tạo đối tượng | Cần kiểu đã được xử lý thích hợp | Thực hiện `new` và constructor | Cấp phát/logical object, quản lý tham chiếu | Có thể được kích hoạt do áp lực cấp phát |
| Mất đường tham chiếu | Không quyết định object liveness | Tiếp tục thực thi chương trình | Root graph không còn giữ đối tượng | Có thể thu hồi ở một đợt GC thích hợp |
| Kết thúc tiến trình | Định nghĩa lớp hết vòng đời theo JVM | Ngừng thực thi | Bộ nhớ tiến trình được hệ điều hành thu hồi | Không cần đợi GC từng đối tượng |

Class Loader và Execution Engine **không thay thế nhau**: loader giải quyết **kiểu và định nghĩa**, engine thực hiện **hành vi**; bộ nhớ lưu trạng thái để cả hai làm việc; GC giúp quản lý sự sống của đối tượng heap.

## 8. Quan sát và chẩn đoán với HotSpot trên JDK 17+

Những lệnh sau là ví dụ công cụ quan sát, **không phải hành vi bắt buộc của mọi JVM**.

```bash
# Hiển thị hoạt động nạp lớp (nhiều log; Java 17+ HotSpot)
java -Xlog:class+load=info JvmFlowDemo

# Hiển thị sự kiện GC (ví dụ này có thể không phát sinh GC)
java -Xlog:gc* JvmFlowDemo

# Ví dụ thiết lập heap cho ứng dụng thực tế; không phải tổng RAM tiến trình
java -Xms256m -Xmx512m JvmFlowDemo
```

Với ứng dụng JVM đang chạy, dùng `jcmd <pid> GC.heap_info` để xem thông tin heap mà triển khai hỗ trợ; `jcmd <pid> Thread.print` giúp xem stack/thread, còn các công cụ profiling/JFR giúp phân tích allocation, pause và CPU. Cần chọn đúng PID và đọc log theo **thời gian/collector thực tế**; đừng dùng một lần chạy ngắn không phát sinh GC để kết luận GC đã bị tắt.

Các dấu hiệu thường gặp cần định vị đúng thành phần:

| Triệu chứng | Hướng điều tra đầu tiên |
| --- | --- |
| `ClassNotFoundException` / `NoClassDefFoundError` | Classpath/module path, class loader, và khác biệt giữa không tìm thấy định nghĩa với lỗi khi liên kết/khởi tạo |
| `ClassCastException` giữa các plugin dù tên kiểu giống nhau | Class identity theo defining loader; dependency/shared API |
| `StackOverflowError` | Đệ quy sâu hoặc vòng gọi lặp, dùng JVM stack |
| `OutOfMemoryError: Java heap space` | Giới hạn/nhu cầu heap, allocation rate, retention graph |
| `OutOfMemoryError: Metaspace` | Class metadata, loader retention, giới hạn Metaspace |
| Pause dài hoặc throughput giảm | GC logs, heap pressure, phân bổ/cấu hình collector; đồng thời kiểm tra tải ứng dụng |
| CPU tăng ở phương thức chạy nhiều | Profiling, hotspot methods, JIT, khóa cạnh tranh; không tự kết luận JIT gây lỗi |

`OutOfMemoryError` có nhiều nguyên nhân ngoài heap; việc tăng `-Xmx` không tự động xử lý class-loader leak, stack overflow, native memory exhaustion hay thread/resource leaks.

## 9. Những nhầm lẫn dễ gặp

1. **“Loader đọc class là chạy constructor ngay.”** Không đúng. Nạp, liên kết và khởi tạo lớp khác với gọi constructor của một **object instance**.
2. **“Mọi đối tượng đều nằm trên stack vì biến cục bộ nằm trong stack.”** Không đúng về mô hình JVM: đối tượng có ngữ nghĩa heap; biến cục bộ có thể chứa tham chiếu. JIT còn có thể tối ưu placement.
3. **“Đặt biến bằng `null` sẽ buộc GC xóa đối tượng.”** Không có cam kết như vậy. Thu hồi dựa trên reachability và collector.
4. **“Không có `free()` nghĩa là không thể rò rỉ bộ nhớ.”** Đối tượng có thể bị giữ bởi cache, listener, queue, `static` hoặc `ThreadLocal` dù không còn cần dùng.
5. **“GC thay cho `close()`.”** GC quản lý chủ yếu bộ nhớ heap; file, socket và connection nên được đóng đúng vòng đời.
6. **“Java được chạy hoàn toàn bằng thông dịch.”** HotSpot có JIT; chiến lược thực thi có thể biến đổi khi chương trình chạy.
7. **“`-Xmx` là toàn bộ giới hạn RAM của JVM.”** Nó chỉ kiểm soát maximum Java heap; còn thread stacks, Metaspace, code cache và native allocations.
8. **“Method area luôn chính là một vùng Java heap tên PermGen.”** Sai với HotSpot hiện đại: PermGen đã được thay bằng Metaspace từ Java 8; JVM spec không bắt buộc chi tiết tổ chức HotSpot.
9. **“Cứ xảy ra GC là toàn bộ thread bị dừng một khoảng giống nhau.”** Phụ thuộc thuật toán và pha GC; có collector làm nhiều việc đồng thời và có những điểm phải tạm dừng ứng dụng.

## 10. Tự kiểm tra khả năng giải thích

- Tại sao in `Config initialized` xảy ra sau `main begins` trong ví dụ, dù `Config` đã được biên dịch cùng chương trình?
- Khi gọi `twice(7)`, frame/biến cục bộ đóng vai trò gì và execution engine làm gì?
- Nếu một cache `static` luôn giữ danh sách đối tượng, vì sao GC chưa thể thu hồi các đối tượng đó?
- Vì sao hai plugin nạp cùng tên lớp nhưng bởi hai defining loader có thể không ép kiểu được cho nhau?
- Khi ứng dụng báo lỗi heap, Metaspace hay stack, vì sao cách xử lý không nên giống hệt nhau?

**Ghi nhớ:** loader xử lý **định nghĩa lớp**; execution engine xử lý **lệnh**; runtime memory giữ **trạng thái và đối tượng**; GC xử lý **đối tượng heap không còn reachable**. Từng thành phần có nhiệm vụ riêng nhưng chỉ có ý nghĩa khi nhìn cùng dòng thực thi.

### Tài liệu chuẩn để tra cứu thêm

- [Java Virtual Machine Specification 17 — Runtime Data Areas (§2.5)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5)
- [Java Virtual Machine Specification 17 — Loading, Linking, and Initializing (Chapter 5)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java Language Specification 17 — Initialization of Classes and Interfaces (§12.4)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4)
