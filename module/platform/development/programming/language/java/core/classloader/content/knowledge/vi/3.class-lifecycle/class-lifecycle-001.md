# Thời điểm JVM cần tạo và nạp một lớp hoặc interface

Khi đọc hoặc thực thi chương trình Java, JVM không nhất thiết nạp mọi lớp và interface xuất hiện trong mã nguồn ngay từ đầu. JVM tạo các **định nghĩa kiểu ở runtime** theo nhu cầu thực thi, theo quá trình liên kết, theo yêu cầu của thư viện như reflection, và có thể nạp một số kiểu sớm hơn để tối ưu. Điều thiết yếu là hiểu **khi nào JVM cần có một kiểu** và **khi nào kiểu đó thực sự được khởi tạo**.

Bài này giải thích chính xác hai từ trong đề:

- **Tạo một lớp/interface ở JVM** (*class/interface creation*, theo JVM Specification): dựng biểu diễn runtime của một **kiểu** đã được xác định bằng tên và defining class loader. Đây **không phải** việc gọi `new` để tạo một đối tượng ứng dụng.
- **Nạp lớp/interface** (*class/interface loading*): dùng cơ chế class loader tìm biểu diễn nhị phân (thường từ tệp `.class`, JAR, module hoặc nguồn bytecode khác), rồi nhờ JVM tạo định nghĩa runtime cho kiểu đó. Với **array class**, JVM có quy tắc tạo đặc biệt, không cần tệp `.class` của array.

Ví dụ, JVM có thể đã tạo định nghĩa kiểu `com.acme.Order` và trả về `Order.class` mà vẫn chưa chạy bất kỳ `static` initializer nào của `Order`, và chưa hề có một đối tượng `new Order()` nào.

## 1. Bốn thời điểm phải tách biệt

```text
Chương trình tham chiếu một kiểu T
          |
          v
    Loading / Creation
  tìm/định nghĩa T trong JVM
          |
          v
         Linking
  verification -> preparation -> resolution (*)
          |
          v
     Initialization (khi có trigger)
  chạy khởi tạo static của T
          |
          v
    Tạo instance (chỉ khi cần)
  new T(...) / cơ chế tạo đối tượng tương ứng

(*) Resolution có thể làm dần khi các tham chiếu được sử dụng.
    Đây là sơ đồ quan hệ, không phải lịch bắt buộc mọi bước đều
    xuất hiện liên tục ngay trong một lần thực thi.
```

| Khái niệm | JVM cần làm gì? | Kết quả quan sát được |
|---|---|---|
| **Loading / creation** | Nhận diện kiểu, tìm bytecode nếu là kiểu thông thường và dựng biểu diễn kiểu runtime | Có đại diện `Class<?>`; có thể xảy ra khi JVM giải quyết một tham chiếu kiểu |
| **Verification** | Kiểm tra ràng buộc hợp lệ của biểu diễn bytecode | Bytecode sai có thể dẫn đến `VerifyError` |
| **Preparation** | Chuẩn bị vùng chứa trường `static` với giá trị mặc định hoặc giá trị theo `ConstantValue` khi thích hợp | Chưa đồng nghĩa chạy mọi biểu thức khởi tạo `static` |
| **Resolution** | Chuyển symbolic reference thành tham chiếu runtime cụ thể, áp dụng kiểm tra kiểu/quyền truy cập | Lúc dùng tham chiếu có thể thấy `NoClassDefFoundError`, `NoSuchMethodError`, `IllegalAccessError`… |
| **Initialization** | Thực hiện logic khởi tạo `static` (phương thức khởi tạo lớp `<clinit>` nếu có) | Log từ `static { ... }` hoặc phương thức được gọi khi gán trường `static` |
| **Instance creation** | Cấp phát/khởi tạo một đối tượng của lớp cụ thể | Constructor, trạng thái mới của từng instance |

**Quy tắc cần nhớ:** *Đã nạp* không có nghĩa *đã khởi tạo lớp*; *đã khởi tạo lớp* không có nghĩa *đã tạo một instance*; và *tạo instance* không đồng nghĩa *nạp lại lớp từ bytecode*.

### Ngữ nghĩa “cần” khác với “chắc chắn mới bắt đầu nạp ngay lúc đó”

Có hai mức cần phân biệt:

1. **Yêu cầu của ngữ nghĩa chương trình:** Khi JVM phải sử dụng thông tin của kiểu T để thực thi hợp lệ (ví dụ giải quyết tham chiếu phương thức/trường hoặc kiểm tra kiểu), JVM phải có được định nghĩa kiểu T tương ứng trước khi thao tác đó hoàn tất.
2. **Lịch thực thi do JVM lựa chọn:** JVM có thể chuẩn bị trước, nạp sớm kiểu phụ thuộc, hoặc trì hoãn việc resolution. Vì thế không thể suy ngược từ một dòng Java rằng **chính xác** trong dòng đó JVM mới đọc `T.class` lần đầu.

Ngược lại, quy tắc **khởi tạo lớp/interface** chặt chẽ hơn: Java quy định rõ các trường hợp sử dụng chủ động dẫn tới initialization. Khi muốn chứng minh thứ tự, hãy quan sát `static` initializer; khi muốn xem hoạt động tải thực tế, hãy dùng công cụ log tải lớp của JVM.

## 2. JVM bắt đầu tạo/nạp lớp từ đâu?

Theo JVM Specification, khi khởi động JVM chọn một **initial class hoặc interface**, tạo và liên kết kiểu ban đầu đó, khởi tạo theo các quy tắc liên quan, rồi chạy entry point thích hợp (ví dụ `main`). Trong khi mã thực thi, những tham chiếu tới các kiểu khác tiếp tục dẫn tới công việc nạp hoặc liên kết.

Một định nghĩa kiểu T có thể được tạo từ các nguyên nhân chính sau:

- **Tham chiếu ký hiệu từ một lớp/interface khác:** Ví dụ bytecode của lớp D chứa symbolic reference tới T trong run-time constant pool. Khi JVM cần xử lý tham chiếu ấy trong quá trình thực thi hoặc linking/resolution, JVM có thể phải tạo/nạp T.
- **API thư viện yêu cầu tra cứu kiểu:** Ví dụ `Class.forName(...)`, `ClassLoader.loadClass(...)`, framework reflection, service/provider loading hoặc mã plugin tự xây dựng.
- **Tạo lớp mảng:** JVM tạo array class theo quy tắc riêng khi kiểu mảng tương ứng cần hiện diện; kiểu component có thể cần nạp, nhưng **không vì thế mà tự động initialize lớp component**.
- **Kiểu được định nghĩa từ nguồn bytecode động:** Custom loader dùng API `defineClass` hoặc cơ chế định nghĩa lớp hợp lệ khác. Đây vẫn là việc tạo **định nghĩa kiểu**, độc lập với việc gọi constructor instance.

Điểm xuất phát quan trọng không phải là “tệp nào đang nằm trên đĩa”, mà là **một symbolic reference hoặc lời gọi API yêu cầu kiểu nào trong không gian của loader nào**.

### Vai trò của symbolic reference và constant pool

Tệp `.class` không nhúng sẵn con trỏ đối tượng Java tới mọi lớp sử dụng. Nó chứa tên và symbolic references, ví dụ tham chiếu tới kiểu, field, method hoặc một entry liên quan đến lời gọi phương thức.

```text
Bytecode của Caller
  constant pool:
    #... Class com/acme/Service
    #... Methodref com/acme/Service.run:()V
               |
               | resolution khi cần
               v
  Kiểu com.acme.Service đã được định nghĩa bởi loader phù hợp
               |
               v
  Tham chiếu tới method/field runtime có thể sử dụng
```

JVM phải bảo đảm ràng buộc type safety, verification và access control. Khi không có định nghĩa đúng của T, thao tác liên quan có thể thất bại ở thời điểm JVM cố sử dụng kiểu đó. Không nên mặc định tất cả symbolic references đều được resolve tại một thời điểm duy nhất.

## 3. Những thao tác Java có thể dẫn tới tải hoặc giải quyết kiểu

Các ví dụ sau xem xét lớp `Service` là một kiểu ứng dụng bình thường và giả định nó chưa được nạp bởi loader cần thiết.

### 3.1. Sử dụng `new`

```java
Service service = new Service();
```

Lệnh `new` ở bytecode phải giải quyết kiểu `Service` và cần thông tin kiểu để tạo instance. Nếu chưa có định nghĩa kiểu này, JVM sẽ nạp/tạo nó qua cơ chế loader. Trước khi instance được khởi tạo xong, `Service` cần được initialized (nếu chưa); sau đó constructor được gọi.

**Không suy ra** mỗi lần `new Service()` đều nạp lại `Service`. Khi định nghĩa lớp đã tồn tại và initialized, các lần `new` kế tiếp tạo đối tượng mới dùng chung định nghĩa runtime đó.

### 3.2. Đọc/ghi trường `static` và gọi phương thức `static`

```java
int current = Service.counter;
Service.counter = 10;
Service.refresh();
```

Để giải quyết trường hoặc phương thức, JVM cần định nghĩa của lớp/interface thực sự khai báo thành viên đó. Khi việc sử dụng là một trigger initialization theo quy tắc Java, JVM phải khởi tạo kiểu khai báo thành viên trước thao tác. Với truy cập `static`, sự khởi tạo thuộc về **kiểu khai báo thành viên đã được resolve**, không nhất thiết là kiểu có tên ở vế trái trong mã nguồn.

**Ngoại lệ thường bị bỏ qua:** đọc *compile-time constant variable* không cần initialize kiểu khai báo. Ví dụ `static final int PORT = 8080;` có thể được trình biên dịch chèn thẳng giá trị vào bytecode của caller. Nhưng `static final int PORT = readPort();` **không** phải constant variable và việc đọc trực tiếp trường này là sử dụng chủ động.

### 3.3. Toán tử và kiểm tra kiểu

```java
boolean ok = value instanceof Service;
Service s = (Service) value;
Class<Service> type = Service.class;
```

Những thao tác này có thể đòi hỏi JVM có thông tin runtime về `Service` để thực hiện kiểm tra kiểu hoặc tạo biểu diễn `Class`. **Chúng không tự động yêu cầu initialize `Service`.**

Với `instanceof` và ép kiểu, một số trường hợp được tối ưu hoặc tham chiếu đã được giải quyết từ trước, nên không nên tuyên bố **mỗi lần thực thi** phép kiểm tra đều tạo/nạp lớp mới. Nếu lớp đích không hiện diện hoặc không giải quyết được, thao tác liên quan có thể gặp lỗi liên kết khi cần.

### 3.4. Reflection và yêu cầu nạp theo tên

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> a = loader.loadClass("com.acme.Service");
Class<?> b = Class.forName("com.acme.Service", false, loader);
Class<?> c = Class.forName("com.acme.Service");
```

Đây là **mảnh minh họa API**, không phải chương trình độc lập; nó chỉ thành công nếu loader tương ứng thực sự tìm được tên nhị phân đó.

- `loader.loadClass(name)` yêu cầu loader tìm/nạp kiểu; theo hành vi mặc định nó **không yêu cầu initialize** lớp. Gọi loader này cũng không bảo đảm nó là defining loader nếu có cơ chế ủy quyền.
- `Class.forName(name, false, loader)` yêu cầu tìm/nạp và liên kết kiểu nhưng **không yêu cầu initialize**.
- `Class.forName(name)` với phiên bản một tham số thường sử dụng loader của caller và **yêu cầu initialize** kiểu (theo tài liệu API), nếu chưa khởi tạo.

Không phương thức nào trong ba dòng trên tự tạo instance `Service`. Phải tách biệt `Class<?>` được trả về với `new Service()` hoặc thao tác constructor bằng reflection.

### 3.5. Loading bởi framework, plugin, dependency injection

Một framework có thể đọc tên lớp từ cấu hình, tra cứu annotation, mở metadata và gọi `loadClass` hoặc `Class.forName`. Một plugin loader cũng có thể định nghĩa lớp trực tiếp từ bytecode của JAR.

Điểm cần quan sát:

- **Metadata inspection** có thể chỉ yêu cầu định nghĩa kiểu mà chưa initialize nó.
- **Bean/service instantiation** có thể làm lớp được initialize và tạo instance.
- **Custom class loader** quyết định không gian tên: cùng binary name nhưng hai defining loader khác nhau có thể dẫn đến hai kiểu runtime không tương thích nhau.

Hãy đọc API cụ thể của framework để biết nó có chủ động initialize lớp hay không; không nên suy đoán chỉ vì framework đã biết tên lớp.

## 4. Array class là trường hợp tạo kiểu đặc biệt

Ví dụ:

```java
Service[] services = new Service[3];
Class<?> arrayType = Service[].class;
Class<?> componentType = arrayType.getComponentType();
```

JVM có định nghĩa runtime riêng cho kiểu mảng `Service[]`. **Array class do JVM tạo**, không có một tệp `Service[].class` trên đĩa để loader đọc.

Nếu component là kiểu tham chiếu, JVM cần có kiểu component tương ứng và gắn defining loader của array class với defining loader của component. Nếu component là primitive, array class gắn với bootstrap loader theo quy định JVM. Các mảng có số chiều khác nhau là các kiểu khác nhau: `Service[]` và `Service[][]` không có cùng `Class`.

**Tạo mảng đối tượng không tạo các phần tử đối tượng và không tự initialize component class.** `new Service[3]` tạo một đối tượng mảng có ba phần tử `null`; nó không tương đương chạy `new Service()` ba lần.

Đối với mảng, phân biệt:

| Thao tác | Tạo instance của `Service`? | Có thể tạo/đụng tới kiểu mảng? | Bắt buộc initialize `Service` chỉ vì thao tác đó? |
|---|---|---|---|
| `Service[].class` | Không | Có | Không |
| `new Service[3]` | Không | Có | Không |
| `services[0] = new Service()` | Có | Mảng đã tồn tại | Có, nếu chưa initialized |
| `int[].class` | Không áp dụng | Có, array class của primitive | Không áp dụng |

## 5. Thí nghiệm Java 17+: thấy rõ thời điểm initialization

Vì **loading có thể xảy ra sớm**, một log trong `static` initializer chỉ cho thấy **initialization**, không phải thời điểm chính xác JVM đọc tệp `.class`. Chương trình dưới đây cố ý tách các hành vi ấy.

Tạo tệp **`LoadingMomentsDemo.java`**:

```java
public class LoadingMomentsDemo {
    static class Service {
        static final int VERSION = 3; // compile-time constant
        static final int PORT = port();

        static {
            System.out.println("Service.<clinit> block");
        }

        static int port() {
            System.out.println("Service.port()");
            return 8080;
        }

        Service() {
            System.out.println("Service constructor");
        }
    }

    interface Feature {
        int VALUE = trace(); // không phải compile-time constant

        static int trace() {
            System.out.println("Feature initialized");
            return 7;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> mirror = Service.class;
        System.out.println("Class literal ready");

        ClassLoader loader = LoadingMomentsDemo.class.getClassLoader();
        Class<?> loaded = loader.loadClass(mirror.getName());
        System.out.println("Same Class: " + (mirror == loaded));

        System.out.println("Constant: " + Service.VERSION);

        Service[] slots = new Service[2];
        System.out.println("Array length: " + slots.length);

        Class.forName(mirror.getName(), false, mirror.getClassLoader());
        System.out.println("forName(false) returned");

        System.out.println("Port: " + Service.PORT);
        new Service();

        System.out.println("Feature value: " + Feature.VALUE);
    }
}
```

Biên dịch/chạy:

```bash
javac LoadingMomentsDemo.java
java LoadingMomentsDemo
```

**Stdout chuẩn:**

```text
Class literal ready
Same Class: true
Constant: 3
Array length: 2
forName(false) returned
Service.port()
Service.<clinit> block
Port: 8080
Service constructor
Feature initialized
Feature value: 7
```

**Giải thích từng mốc:**

1. `Service.class` cho phép lấy `Class<?>`. Chưa có output của `Service`: literal không tự buộc chạy initializer.
2. `loader.loadClass(mirror.getName())` dùng loader thích hợp tìm cùng định nghĩa lớp; kết quả mirror bằng nhau. Mã này không yêu cầu initialize `Service`.
3. `Service.VERSION` là constant variable (`static final int` gán từ constant expression). Caller có thể dùng trực tiếp giá trị `3`, không kích hoạt initializer của `Service`.
4. `new Service[2]` tạo một **array instance** có hai slot `null`. JVM có kiểu mảng và thông tin component, nhưng vẫn chưa phải khởi tạo `Service`.
5. `Class.forName(name, false, loader)` trả về mà không yêu cầu initialize `Service`.
6. **Đọc `Service.PORT` lần đầu** là sử dụng chủ động một trường `static` không phải constant variable. JVM initialize `Service`: chạy `port()` trước rồi đến `static` block theo thứ tự mã nguồn; vì vậy hai dòng log xuất hiện trước `Port: 8080`.
7. `new Service()` sau đó chạy constructor và in `Service constructor`, nhưng không chạy lại initializer `static`.
8. `Feature.VALUE` cũng không phải constant variable. Lần đọc trường kích hoạt initialize interface `Feature`: `trace()` in một dòng rồi giá trị `7` được in.

**Vì sao “Same Class: true” đáng tin?** Cả `Service` và `LoadingMomentsDemo` được định nghĩa từ cùng đơn vị mã ứng dụng do cơ chế loader tương ứng, và loader này trả đúng cùng `Class<?>` mà `Service.class` biểu diễn. Chương trình không dựa vào tên class loader phụ thuộc JDK.

Chương trình minh họa **thời điểm JVM bắt buộc initialize** lớp/interface; nó không cố khẳng định bytecode `Service` được đọc lần đầu đúng tại `Service.class`.

### Quan sát loading thật trên HotSpot

Với HotSpot JVM/JDK 17+, có thể dùng Unified Logging:

```bash
java -Xlog:class+load=info LoadingMomentsDemo
```

Các dòng log gắn với tên kiểu và nguồn nạp giúp tìm lúc JVM **ghi nhận sự kiện nạp**. Output log này phụ thuộc JDK, JVM, cấu hình module/classpath và runtime; không thể coi một thứ tự nạp phụ thuộc triển khai là hợp đồng của chương trình.

Có thể dùng thêm `javap -c -v LoadingMomentsDemo` để tìm những symbolic references và bytecode như `ldc`, `getstatic`, `anewarray`, `new`, `invokestatic`. Đây là công cụ phân tích bytecode, không thay thế việc quan sát JVM runtime.

## 6. Khác biệt quan trọng: loading không phải initialization

Một bảng quyết định nhanh:

| Cú pháp/thao tác | Có thể cần nạp/liên kết kiểu T? | Có bắt buộc initialize T chỉ vì thao tác này? | Có tạo instance T? |
|---|---|---|---|
| `T.class` | Có | **Không** | Không |
| `Class.forName("pkg.T", false, loader)` | Có, chủ động yêu cầu lookup/loading/linking | **Không yêu cầu** | Không |
| `loader.loadClass("pkg.T")` | Có, chủ động yêu cầu lookup/loading | **Không yêu cầu** | Không |
| `Class.forName("pkg.T")` | Có | **Có**, theo overload này nếu chưa initialized | Không |
| `new T()` với T là class cụ thể | Có | **Có**, trước khi tạo đối tượng hoàn tất | **Có** |
| `T.staticMethod()` với method do T khai báo | Có | **Có**, nếu chưa initialized | Không |
| `T.nonConstantStaticField` đọc/ghi, khai báo ở T | Có | **Có**, nếu chưa initialized | Không |
| `T.COMPILE_TIME_CONSTANT` | Không nhất thiết | **Không** | Không |
| `new T[10]` | Có thể cần component type và array type | **Không** initialize component T | Không tạo T; tạo array instance |
| `value instanceof T` hoặc cast `(T) value` | Có thể cần resolve T | **Không** | Không |

**Lưu ý về các ô “Có”:** bảng diễn tả **yêu cầu khi thao tác cần kiểu**, không bảo đảm mỗi lần thực thi sẽ sinh một sự kiện đọc bytecode mới. Kiểu có thể đã nạp, liên kết hoặc khởi tạo trước đó.

**Lưu ý về `Class.forName`:** mô tả trên áp dụng cho các overload được ghi rõ trong bảng; API còn có overload dựa trên module với semantics riêng. Luôn nhìn đúng chữ ký phương thức.

## 7. Các ngộ nhận thường gặp

1. **“Java nạp mọi class trên classpath khi chạy `main`.”** Không đúng: classpath chứa các ứng viên có thể nạp; nhu cầu thực thi/liên kết, thư viện và chiến lược JVM quyết định định nghĩa nào xuất hiện.
2. **“Đọc một dòng `T.class` chắc chắn làm chạy `static` block của T.”** Sai: lấy class literal tự nó không kích hoạt initialization.
3. **“JVM chỉ có thể tải lớp đúng tại lần dùng đầu tiên.”** Sai: JVM được phép chọn tải/liên kết sớm nếu bảo toàn ngữ nghĩa quan sát được.
4. **“Nạp class luôn tạo object T.”** Sai: loading tạo biểu diễn kiểu runtime; instance của T là câu chuyện khác.
5. **“`ClassLoader.loadClass` và `Class.forName(String)` giống nhau.”** Sai về yêu cầu initialization theo các overload được đề cập.
6. **“Tạo `new T[5]` tương đương năm lần `new T()`.”** Sai: array có các slot mặc định `null`; chưa có instance T nào được tạo.
7. **“Interface không bao giờ initialize.”** Sai: truy cập trường không phải constant variable hoặc gọi static method có thể kích hoạt initialization của interface.
8. **“Implements một interface là luôn initialize interface ấy.”** Sai: loading/liên kết quan hệ kiểu và initialization của interface khác nhau; đặc biệt chú ý quy tắc superinterface có default method khi class initialize.
9. **“Một binary name chỉ có một kiểu trên cả JVM.”** Sai: defining loader là một phần của danh tính kiểu runtime.
10. **“Dòng log từ `static` block cho biết chính xác khi nào class file được đọc.”** Sai: log ấy chỉ phản ánh initialization.

## 8. Tự kiểm tra

**Câu 1.** JVM cần chạy `T.class` trong chương trình, nhưng `T` chưa được initialized. Có bắt buộc gọi `<clinit>` ngay không?

**Đáp án:** Không. JVM có thể phải định nghĩa/đã định nghĩa T để cung cấp `Class<?>`, nhưng chỉ `T.class` không phải trigger khởi tạo T.

**Câu 2.** Tại sao `Class.forName("pkg.Plugin", false, loader)` vẫn hữu ích nếu không tạo instance?

**Đáp án:** Vì nó yêu cầu lookup/loading/linking để biết kiểu `Plugin` tồn tại trong không gian của loader nào; ứng dụng sau đó có thể kiểm tra kiểu, metadata, constructor, hoặc quyết định tạo đối tượng về sau.

**Câu 3.** Nếu `interface I { int A = 10; int B = compute(); ... }`, chỉ đọc `I.A` và `I.B` có kết quả initialization giống nhau không?

**Đáp án:** Không. `I.A` là compile-time constant và có thể inline; `I.B` không phải constant variable nên truy cập trực tiếp nó là trigger initialize I.

**Câu 4.** Mã `new Widget[4]` có bắt buộc gọi constructor `Widget()` bốn lần không?

**Đáp án:** Không. Nó tạo mảng bốn phần tử tham chiếu, mỗi phần tử ban đầu là `null`.

**Câu 5.** Cùng `p.Widget` nhưng hai class loader thật sự định nghĩa hai bản riêng: có phải một kiểu duy nhất không?

**Đáp án:** Không. JVM xét tên nhị phân cùng defining loader để xác định kiểu runtime; hai định nghĩa là hai kiểu riêng.

## 9. Bản đồ quyết định khi đọc một thao tác Java

```text
JVM gặp một tham chiếu đến kiểu T
            |
            v
Kiểu T đã được định nghĩa trong loader cần dùng?
        /             \
      chưa             rồi
       |                |
Tìm biểu diễn nhị phân  Dùng định nghĩa đã có
và định nghĩa T             |
       \                   /
        v                 v
      Kiểm tra/link/resolve phù hợp
                    |
                    v
      Có trigger khởi tạo T không?
             /              \
           không             có
             |                |
     Dùng thông tin kiểu   Initialize T nếu cần
             |                |
             +--------+-------+
                      |
                      v
       Có thực sự tạo instance T không?
                 /          \
               không         có
                |            |
      Không có T object    Tạo đối tượng cụ thể
```

Ba câu hỏi hữu ích khi phân tích runtime là: **JVM cần kiểu nào? Loader nào định nghĩa kiểu đó? Thao tác nào buộc initialization hoặc tạo instance?** Trả lời tách biệt ba câu hỏi sẽ tránh nhầm thời điểm nạp class với thời điểm chạy static initializer hay constructor.

### Đọc thêm từ đặc tả chính thức

- [JVM Specification, 5.2–5.5: Startup; Creation and Loading; Linking; Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java Language Specification, 12.2–12.5: Loading; Linking; Initialization; Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html)
