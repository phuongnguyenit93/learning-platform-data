# Handle đã tạo và Lookup có quyền cao: giới hạn phạm vi chia sẻ trong thiết kế thư viện

## 1. Bài toán: ai giữ quyền sau khi tạo MethodHandle?

Trong mô-đun **JAVA_VERSION_JAVA18**, chúng ta tìm hiểu những hành vi của Java 18 vẫn hữu ích trên JDK hiện đại, gồm UTF-8 mặc định, simple web server, Javadoc snippet và cách kiểm chứng hợp đồng API của resolver, reflection, `MethodHandle`. Bài này thuộc chương **Lookup và adapter**, tập trung vào câu hỏi thực tế trong thiết kế thư viện: **nếu mã có quyền cao tạo một handle đến private member rồi đưa handle đó cho mã khác, quyền gọi có đi theo handle không?**

Câu trả lời quan trọng: một `MethodHandle` đã được tạo thành công có thể được **truyền và gọi ở nơi khác** theo kiểu phương thức và điều kiện của target. Các kiểm tra quyền cần thiết để *tra cứu hoặc tạo handle* được thực hiện trong quá trình tạo; khi caller khác gọi handle đã nhận, JVM không làm lại phép kiểm tra quyền truy cập private **dựa trên lớp caller mới** như khi chính caller đó thực hiện `findVirtual`. Vì thế một handle có thể là **năng lực truy cập (*capability*)** tới hành vi mà phía nhận không tự tra cứu được.

Đối tượng `MethodHandles.Lookup` còn nhạy cảm hơn: một `Lookup` mang theo các quyền tra cứu thích hợp có thể được dùng để **tạo thêm những handle khác** tới thành viên mà quyền đó cho phép. Việc làm lộ một `Lookup` giàu quyền có thể vô tình mở rộng tập member mà phía nhận truy cập được.

Sau bài này, bạn có thể:

- Phân biệt **quyền tra cứu** của `Lookup` với **quyền gọi** của `MethodHandle` đã được tạo.
- Giải thích vì sao `MethodHandles.lookup()` phụ thuộc lớp đang gọi và vì sao trả `Lookup` từ một phương thức thư viện có thể làm lộ quyền của thư viện.
- Kiểm chứng rằng chia sẻ handle tới private member khác với chia sẻ `Lookup` cho phép tiếp tục tra cứu.
- Phân tích `bindTo`, `asType` và các adapter: chúng đổi hình thức gọi, nhưng không tự khôi phục kiểm tra quyền theo caller mới.
- Thiết kế API công khai theo những thao tác cụ thể thay vì vô tình cho bên ngoài truy cập tất cả thành viên private.
- Nhận diện giới hạn của `privateLookupIn`, `publicLookup` và JPMS trên JDK hiện đại.

## 2. Hai loại đối tượng thường bị đánh đồng

### 2.1. Lookup là quyền *tìm và tạo* member handle

Một `MethodHandles.Lookup` là đối tượng mô tả **lớp tra cứu** (`lookupClass()`) và các **quyền truy cập** (`lookupModes()`). Ví dụ:

```java
MethodHandles.Lookup local = MethodHandles.lookup();

System.out.println(local.lookupClass());
System.out.println(local.lookupModes());
System.out.println(local.hasFullPrivilegeAccess());
```

`MethodHandles.lookup()` là API có ngữ cảnh caller: khi gọi trực tiếp **bên trong một phương thức của lớp thư viện**, nó tạo `Lookup` có danh tính/quyền liên quan đến lớp thư viện đó, **không tự động mang danh tính của lớp đã gọi vào phương thức thư viện**. Điều này đặc biệt quan trọng với phương thức trả về `Lookup`.

Một `Lookup` có đủ quyền có thể dùng các thao tác như:

- `findStatic`, `findVirtual`, `findConstructor` để tạo handle gọi phương thức/hàm tạo.
- `findGetter`, `findSetter` để tạo handle truy cập trường, nếu các quy tắc truy cập và thuộc tính trường cho phép.
- `unreflect` và các thao tác liên quan để tạo handle từ metadata reflection trong phạm vi quyền thích hợp.
- `privateLookupIn`, khi thỏa các điều kiện được API và JPMS quy định, để nhận lookup phù hợp cho lớp đích.

Không suy ra quyền chỉ từ việc có một biến kiểu `Lookup`. Một lookup bị giới hạn quyền và một lookup đầy đủ quyền có thể tạo ra kết quả rất khác nhau. `lookupModes()` hữu ích cho chẩn đoán, nhưng việc kiểm thử thao tác cụ thể trên đúng module/JDK vẫn cần thiết.

### 2.2. MethodHandle là năng lực *gọi hành vi đã chọn*

Ví dụ:

```java
MethodHandle handle = lookup.findVirtual(
        Service.class,
        "execute",
        MethodType.methodType(String.class, String.class));
```

Khi tạo thành công, `handle` ghi nhận target cùng kiểu phương thức. Với instance method, kiểu handle có **tham số receiver đầu tiên**, nên ví dụ có kiểu `(Service, String)String`. Caller nhận handle có thể gọi:

```java
String result = (String) handle.invokeExact(service, "request");
```

Điều kiện kiểu ở `invokeExact` vẫn phải khớp chính xác; target cũng có thể ném ngoại lệ, hoặc thất bại nếu receiver null. Đây là những điều kiện **của lời gọi handle**, không phải bước tra cứu lại `execute` bằng quyền private của lớp caller hiện tại.

### 2.3. So sánh nhanh

| Được chia sẻ | Phía nhận có gì? | Rủi ro chính |
| --- | --- | --- |
| Chỉ chuỗi tên member | Thông tin tên, chưa có handle hay quyền truy cập | Phải tự tìm member bằng quyền của mình |
| `MethodHandle` tới một private method | Năng lực gọi **target cụ thể** theo kiểu handle | Có thể gọi hành vi nhạy cảm nhiều lần |
| Handle đã `bindTo` một receiver | Năng lực gọi target với **receiver đã cố định** | Có thể truy cập hành vi nhạy cảm trên đối tượng cụ thể |
| `Lookup` đủ quyền cho lớp thư viện | Có thể tạo **nhiều handle mới** trong phạm vi quyền lookup | Quyền bị mở rộng ngoài hành vi ban đầu được định chia sẻ |
| `publicLookup()` | Lookup bị giới hạn cho các thành viên/kiểu public thích hợp | Không tự truy cập private; vẫn cần thiết kế API public rõ ràng |
| API facade chỉ trả kết quả đã kiểm soát | Chỉ thao tác công khai do thư viện định nghĩa | Không làm lộ raw handle/lookup đến member nội bộ |

## 3. Phân biệt kiểm tra quyền lúc tra cứu và lúc gọi

Giả sử `Vault` có phương thức `private String readSecret()`.

**Phía ngoài chỉ tự dùng lookup của chính mình:**

```java
MethodHandles.lookup().findVirtual(
        Vault.class,
        "readSecret",
        MethodType.methodType(String.class));
```

Nếu caller **không có quyền truy cập private** của `Vault`, thao tác này có thể ném `IllegalAccessException` ngay khi tìm handle. Kiểu đúng không thể thay thế quyền truy cập.

**Mã có quyền bên trong `Vault` tạo handle rồi truyền đi:**

```java
// Viết bên trong Vault, nơi lookup có quyền đối với readSecret():
MethodHandle exposed = MethodHandles.lookup().findVirtual(
        Vault.class,
        "readSecret",
        MethodType.methodType(String.class));
```

Sau khi `exposed` được trao cho mã khác, việc gọi `exposed.invokeExact(vault)` sử dụng **năng lực của handle đã được tạo**. JVM không yêu cầu caller bên ngoài trước tiên phải tự gọi thành công `findVirtual` tới private member đó.

Cách nhìn đúng:

```text
Lớp A có quyền tìm private member
    |
    +-- Lookup của A -- findVirtual --> MethodHandle đã tạo
                                           |
                                           +-- A gọi handle
                                           |
                                           +-- B nhận handle, gọi handle
                                               (cùng target/MethodType;
                                                không lookup private lại theo B)

Lớp B tự gọi findVirtual bằng Lookup của B
    |
    +-- kiểm tra quyền của B tại bước tra cứu
        (có thể IllegalAccessException)
```

**Ranh giới:** Điều này không có nghĩa handle miễn mọi kiểm tra. Kiểu đối số/kiểu kết quả của `invokeExact` vẫn phải khớp, `invoke` chỉ hỗ trợ những chuyển đổi xác định, receiver null vẫn có thể ném `NullPointerException` và target vẫn có thể tự ném ngoại lệ.

## 4. Thí nghiệm chạy được: handle private và Lookup bị chia sẻ

Bài thử dưới đây cố ý có hai phương thức công khai **không nên xuất hiện trong API sản phẩm**: `unsafeExportHandleForDemo` và `unsafeExportLookupForDemo`. Chúng chỉ nhằm quan sát hệ quả của việc chia sẻ quyền. Dữ liệu là chuỗi giả `demo-only`; không dùng token thật trong log.

Lưu thành **`HandleSharingDemo.java`**. `ExternalConsumer` là một **top-level class riêng** trong cùng tệp nguồn, khác nest với `HandleSharingDemo.Vault`. Nó không nhận quyền private theo quan hệ nest.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HandleSharingDemo {
    public static final class Vault {
        private final String secret;

        private Vault(String secret) {
            this.secret = secret;
        }

        private String readSecret() {
            return secret;
        }

        // Đây mới là API công khai có phạm vi hành vi rõ ràng.
        public String publicLabel() {
            return "Vault";
        }

        // CHỈ DÙNG ĐỂ MINH HỌA RỦI RO: lộ một private MethodHandle.
        public static MethodHandle unsafeExportHandleForDemo()
                throws NoSuchMethodException, IllegalAccessException {
            return MethodHandles.lookup().findVirtual(
                    Vault.class,
                    "readSecret",
                    MethodType.methodType(String.class));
        }

        // CHỈ DÙNG ĐỂ MINH HỌA RỦI RO: lộ quyền tra cứu của Vault.
        public static MethodHandles.Lookup unsafeExportLookupForDemo() {
            return MethodHandles.lookup();
        }
    }

    public static Vault createForDemo() {
        return new Vault("demo-only");
    }

    public static void main(String[] args) throws Throwable {
        ExternalConsumer.inspect(createForDemo());
    }
}

// Top-level class khác nest với Vault, dù cùng package và tệp nguồn.
class ExternalConsumer {
    static void inspect(HandleSharingDemo.Vault vault) throws Throwable {
        Class<HandleSharingDemo.Vault> owner =
                HandleSharingDemo.Vault.class;
        MethodType noArgumentsReturnsString =
                MethodType.methodType(String.class);

        // 1. Caller này không có quyền lookup trực tiếp private method.
        try {
            MethodHandles.lookup().findVirtual(
                    owner, "readSecret", noArgumentsReturnsString);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("direct-lookup=IllegalAccessException");
        }

        // 2. Nhưng vẫn gọi được MethodHandle đã được Vault tạo và xuất ra.
        MethodHandle leakedHandle =
                HandleSharingDemo.Vault.unsafeExportHandleForDemo();

        // Kiểu của findVirtual gồm receiver Vault: (Vault)String.
        String fromHandle = (String) leakedHandle.invokeExact(vault);
        System.out.println("exported-handle=" + fromHandle);

        // 3. Một Lookup giàu quyền có thể tạo THÊM handle tới field private.
        MethodHandles.Lookup leakedLookup =
                HandleSharingDemo.Vault.unsafeExportLookupForDemo();

        MethodHandle getter =
                leakedLookup.findGetter(owner, "secret", String.class);

        String fromDerivedHandle = (String) getter.invokeExact(vault);
        System.out.println("derived-getter=" + fromDerivedHandle);

        // 4. bindTo bỏ tham số receiver khỏi kiểu gọi, không gỡ quyền.
        MethodHandle bound = leakedHandle.bindTo(vault);
        String fromBound = (String) bound.invokeExact();
        System.out.println("bound-handle=" + fromBound);

        // 5. publicLookup chỉ tra cứu API public thích hợp.
        MethodHandle safePublicHandle =
                MethodHandles.publicLookup().findVirtual(
                        owner, "publicLabel", noArgumentsReturnsString);

        String label = (String) safePublicHandle.invokeExact(vault);
        System.out.println("public-api=" + label);
    }
}
```

Biên dịch và chạy trên JDK 18 trở lên:

```bash
javac HandleSharingDemo.java
java HandleSharingDemo
```

Kết quả dự kiến trong môi trường classpath thông thường:

```text
direct-lookup=IllegalAccessException
exported-handle=demo-only
derived-getter=demo-only
bound-handle=demo-only
public-api=Vault
```

### Vì sao kết quả này đáng chú ý?

- `ExternalConsumer` **không tự tìm được** private method thông qua lookup trực tiếp của chính nó.
- Khi `Vault` trả ra `MethodHandle` đã được tạo với quyền của `Vault`, phía ngoài **gọi được target** dù trước đó không thể tự `findVirtual`.
- Khi `Vault` trả ra `Lookup`, phía ngoài còn tạo được handle **đến trường private `secret`**, mặc dù API minh họa ban đầu chỉ định chia sẻ phương thức `readSecret`.
- `bindTo(vault)` làm handle có kiểu `()String`, vì receiver đã được gắn trước. Bên nhận **không cần tiếp tục giữ biến `vault`** để gọi handle bound; năng lực vẫn còn.
- `publicLookup` tìm được `publicLabel`, một phương thức public có hợp đồng rõ ràng; đây là một cách giới hạn phạm vi tra cứu đối với API public.

**Giới hạn quan trọng của thí nghiệm:** Các lớp ở ví dụ chạy trong **cùng unnamed module**. Việc `MethodHandles.lookup().findVirtual` trực tiếp của `ExternalConsumer` thất bại **không phải bằng chứng rằng class đó bị cô lập tuyệt đối khỏi private member**: trong cùng module, khi thỏa điều kiện API, caller còn có thể yêu cầu `MethodHandles.privateLookupIn` hoặc dùng reflection mở truy cập. Ví dụ này được thiết kế để phân biệt **quyền của lookup trực tiếp**, **quyền của handle được chia sẻ** và **quyền của Lookup được trao**, chứ không phải một security sandbox. Nếu thiết kế ranh giới thư viện giữa các thành phần cần đóng gói nghiêm ngặt, hãy xét cấu trúc **named modules** và các điều kiện `exports`/`opens`.

## 5. Vì sao trả Lookup thường nguy hiểm hơn trả một handle?

Cho một lớp thư viện có nhiều private members:

```java
final class AccountState {
    private String auditCode() { return "..."; }
    private String internalToken() { return "..."; }
    private int revision;
}
```

Một `MethodHandle` chỉ tới `auditCode` cho phép gọi **một hành vi cụ thể** (cộng với những cách thích nghi có thể tạo từ handle đó). Nhưng nếu thư viện trả một `Lookup` đầy đủ quyền đối với `AccountState`, người nhận có thể thử tạo handle tới `internalToken` hay getter `revision`, miễn các quyền hiện có của lookup cho phép.

| Cách chia sẻ | Phạm vi chủ đích | Khả năng bên nhận có thể dùng |
| --- | --- | --- |
| Trả kết quả đã kiểm soát qua public method | Một hành vi cụ thể | Gọi API công khai theo quy tắc thư viện |
| Trả handle tới một private method | Target method được chọn | Gọi method đó, kể cả trong các lần gọi khác nhau |
| Trả handle đã `bindTo` receiver | Một hành vi trên một đối tượng cụ thể | Gọi target bằng receiver đã gắn |
| Trả `Lookup` có quyền private | Một lớp/khu vực có thể tra cứu tiếp | Tạo thêm handle tới những member khác trong phạm vi quyền |

**Không coi `Lookup` chỉ là một trình tạo cú pháp tiện lợi.** Nó chứa thông tin quyền truy cập có ý nghĩa. Nếu một utility trả `MethodHandles.lookup()` cho caller, đối tượng trả về phản ánh lookup nơi phương thức **utility thực sự gọi `lookup()`**, chứ không phải tự động giảm quyền thành quyền của người nhận.

Việc chỉ đổi tên phương thức từ `unsafeExportLookupForDemo` thành `getLookup()` không làm giới hạn quyền bên trong đối tượng. Chính thiết kế của luồng dữ liệu và cách tạo lookup/handle mới quyết định phạm vi chia sẻ.

## 6. Các adapter có làm quyền trở nên an toàn hơn không?

`MethodHandle` hỗ trợ nhiều bộ thích nghi (*adapter*) để thay đổi cách caller truyền đối số/nhận kết quả. Đây là các API còn được hỗ trợ trên JDK hiện đại, nhưng cần phân biệt **thích nghi kiểu** với **thu hẹp quyền**.

### 6.1. `asType`: thay đổi kiểu được nhìn thấy, không kiểm tra lại quyền private

```java
MethodHandle raw = HandleSharingDemo.Vault
        .unsafeExportHandleForDemo();

// Đổi tham số receiver từ Vault sang Object.
// Khi gọi, adapter sẽ ép kiểu Object về Vault.
MethodHandle adapted = raw.asType(
        MethodType.methodType(String.class, Object.class));

Object receiver = HandleSharingDemo.createForDemo();
String observed = (String) adapted.invokeExact(receiver);
```

Việc tạo adapter `(Object)String` cho phép caller truyền giá trị với kiểu tĩnh `Object`, nhưng không làm target `readSecret` trở thành public hoặc buộc caller phải tự tra cứu lại member. Nếu truyền đối tượng không thuộc kiểu `Vault`, adapter có thể ném `ClassCastException`. Các kiểm tra kiểu/receiver vẫn tồn tại, còn năng lực target được giữ.

### 6.2. `bindTo`: cố định receiver, thu hẹp đối tượng nhưng giữ khả năng gọi

```java
MethodHandle original = HandleSharingDemo.Vault
        .unsafeExportHandleForDemo();

HandleSharingDemo.Vault one = HandleSharingDemo.createForDemo();
MethodHandle forOneVault = original.bindTo(one);

// Sau bindTo: ()String.
String secret = (String) forOneVault.invokeExact();
```

`bindTo` tạo một handle mới bằng cách gắn tham số tham chiếu đầu tiên vào một giá trị cụ thể. Nó giới hạn việc gọi vào receiver đã gắn, nhưng **không vô hiệu hóa năng lực gọi private method** trên receiver đó. Vì bound handle giữ tham chiếu tới receiver cần thiết để thực hiện lời gọi, hãy cân nhắc vòng đời đối tượng nếu lưu handle lâu dài.

### 6.3. `insertArguments` và các adapter khác

`MethodHandles.insertArguments` có thể cố định một hoặc nhiều đối số; `filterReturnValue` có thể áp một bước biến đổi sau target; `dropArguments` có thể thêm đối số không dùng đến. Những adapter này phù hợp khi **thiết kế một hành vi public cụ thể**, nhưng bản thân chúng không tạo lại việc kiểm tra quyền theo caller.

Ví dụ, nếu thư viện **chỉ trả** một handle đã lọc kết quả ra thông tin công khai và **giữ kín** handle gốc, bên nhận chỉ có năng lực gọi hành vi của handle đã lọc. Ngược lại, nếu raw handle đã bị trao trước đó, tạo thêm adapter không rút lại được năng lực đã phát tán.

Vì thế câu hỏi cần đặt không phải “adapter có làm handle an toàn không?”, mà là **“sau khi đưa handle này ra khỏi thư viện, caller có thể thực hiện chính xác những hành vi nào?”**

## 7. `publicLookup`, `Lookup.in` và `privateLookupIn`: chọn quyền phù hợp

### `MethodHandles.publicLookup()`

Dùng khi thư viện chỉ cần tra cứu các kiểu và member `public` có thể truy cập theo luật tương ứng:

```java
MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();

MethodHandle size = publicOnly.findVirtual(
        String.class, "length", MethodType.methodType(int.class));
```

Phạm vi của `publicLookup()` bị giới hạn. Nó không tự giải quyết trường hợp cần private member. Ngay cả đối với thành viên public, quyền truy cập còn phụ thuộc khả năng truy cập kiểu khai báo và ranh giới module thích hợp.

### `Lookup.in(Class<?>)` và `dropLookupMode(int)`

Hai API có thể dùng để chuyển lớp tra cứu hoặc chủ động làm giảm quyền theo quy tắc của `Lookup`. **Không suy đoán rằng gọi `in(...)` sẽ tăng quyền đối với lớp mới**: một lookup chuyển ngữ cảnh có thể mất một số quyền. Khi thiết kế cơ chế mở rộng, cần khảo sát `lookupClass()` và `lookupModes()` trên kết quả và kiểm thử đúng member dự kiến.

Nếu không có lý do chính đáng để chuyển một `Lookup` có quyền cao cho mã bên ngoài, phương án đơn giản hơn là **không xuất lookup**. Việc giảm bớt quyền chỉ nên thực hiện dựa trên yêu cầu API cụ thể và được thử trong cấu hình module thực tế.

### `MethodHandles.privateLookupIn(target, callerLookup)`

API này có thể tạo một lookup cho phép truy cập private ở target **khi các điều kiện quyền và JPMS được đáp ứng**. Trong trường hợp xuyên named modules, cần xét quan hệ đọc module, việc package của target được `opens` phù hợp và quyền của lookup được dùng làm đầu vào. Một lookup bị giới hạn quyền không thể tự yêu cầu thêm mọi quyền chỉ bằng cách gọi `privateLookupIn`.

Ví dụ thiết lập module:

```java
module library.core {
    exports com.example.api;
    // Không mở gói nội bộ cho module consumer.
}
```

Ở cấu trúc này, một consumer ở named module khác không thể chỉ dựa vào `exports com.example.api` để tự nhận quyền reflection sâu tới private member trong package không được mở. Nếu thư viện chủ động `opens` một package cho một module kiểm tra, đó là một quyết định cấp quyền cần mô tả rõ. Việc dùng `publicLookup` hoặc trao một handle đã được tạo có phạm vi cụ thể vẫn có vai trò riêng, không thay thế cho thiết kế module.

**Đừng nhầm:** cơ chế JPMS kiểm soát **khả năng tra cứu/reflective access trực tiếp** theo module và quyền; nó không tự ngăn một thư viện **có quyền** chủ động trao capability đã tạo cho bên khác. Trả raw handle tới private method vẫn là hành động cho phép thực thi target, ngay cả khi consumer không có quyền tự tra cứu target đó.

## 8. Cách thiết kế API thư viện với phạm vi chia sẻ rõ ràng

Khi một thư viện cần dùng private method hoặc constructor để phục vụ logic nội bộ, hãy phân biệt hai mục tiêu:

- **Nội bộ thư viện cần năng lực mạnh:** một `Lookup` phù hợp để tìm handle; handle được giữ trong class/đối tượng sở hữu và dùng cho nhu cầu nội bộ.
- **Bên sử dụng thư viện cần hành vi ổn định:** một public method hoặc public interface có hợp đồng đầu vào, đầu ra, kiểm tra tham số và chính sách lỗi rõ ràng.

Một mẫu đơn giản:

```java
public final class TokenLibrary {
    private TokenLibrary() {}

    // Dữ liệu nội bộ chỉ là minh họa.
    private static final String INTERNAL = "demo-only";

    private static String sensitiveOperation() {
        return INTERNAL;
    }

    // Public API được định nghĩa có chủ đích: chỉ trả nhãn công khai.
    public static String publicSummary() {
        return "TokenLibrary ready";
    }

    // Không xuất MethodHandles.lookup() hoặc handle
    // của sensitiveOperation() ở public API.
}
```

Nếu ứng dụng cần callback dưới dạng `MethodHandle`, chỉ trả một handle tới **hành vi đã được phê duyệt cho bên nhận** và giữ kín các handle/lookup có quyền cao khác. Kiểm tra chính xác `MethodType` và cách caller sử dụng `invokeExact`/`invoke`. Một handle tới phương thức public đã chọn thường dễ kiểm soát phạm vi hơn một lookup có thể dùng để tìm thêm member.

Các nguyên tắc thực hành:

1. **Hạn chế xuất `Lookup` có quyền cao.** Không dùng phương thức public `getLookup()` chỉ để tiết kiệm vài dòng code ở phía consumer.
2. **Hạn chế xuất raw handle private.** Đã trao handle là đã trao năng lực gọi target trong phạm vi kiểu/receiver phù hợp.
3. **Giữ handle nhạy cảm trong phạm vi nội bộ.** Ví dụ lưu trong `private static final` khi thích hợp, đồng thời tránh trả qua API public hoặc callback ngoài ý muốn.
4. **Xuất khả năng tối thiểu cần dùng.** Nếu consumer chỉ cần một kết quả, trả kết quả hoặc một public interface với chính sách cụ thể.
5. **Đối với bound handle, xem xét receiver và vòng đời.** `bindTo` có thể giữ đối tượng đích, làm tăng thời gian đối tượng tồn tại.
6. **Không xem adapter là cơ chế cấp/rút quyền tổng quát.** `asType` thay đổi kiểu, `bindTo` cố định đối số; chúng không sửa quan hệ quyền tại thời điểm handle gốc được tạo.
7. **Ghi rõ ranh giới module.** Dùng `exports` cho API public và `opens` có chọn lọc khi thật sự cần deep reflection. Không dùng kết quả chạy classpath làm giả định mặc định cho mọi named module.

Nếu cần một cơ chế thu hồi khả năng gọi, thư viện phải thiết kế trạng thái kiểm tra riêng trong hành vi được xuất (chẳng hạn callback kiểm tra trạng thái tại mỗi lời gọi). **Thu hồi tham chiếu tới biến handle trong thư viện không thu hồi được các bản tham chiếu handle đã trao**; việc chỉ thay đổi field đang giữ handle không làm vô hiệu hóa các handle cũ nằm ở consumer.

## 9. Kiểm thử giới hạn quyền như một hợp đồng thư viện

Một bộ test nên có hai lớp kiểm chứng: **khả năng tra cứu** và **hành vi sau khi trao capability**. Không chỉ dựa vào việc `findVirtual` thất bại từ một caller.

| Kịch bản | Cách thử | Kết luận hợp lệ |
| --- | --- | --- |
| Caller khác nest tự tra cứu private method | Gọi `findVirtual` bằng `MethodHandles.lookup()` của caller | Biết caller đó có đủ quyền tra cứu trực tiếp hay không |
| Thư viện tạo handle rồi trao ra | Caller gọi handle theo `MethodType` được cung cấp | Biết capability cụ thể đã cho phép thực hiện target |
| Thư viện trao `Lookup` | Caller thử tạo getter/handle tới member thứ hai | Phát hiện phạm vi tra cứu thêm do lookup được chia sẻ |
| Handle đã `bindTo` | Gọi mà không truyền receiver | Xác định receiver đã được gắn và năng lực vẫn hoạt động |
| Chuyển handle bằng `asType` | Gọi với kiểu call site đã thay đổi | Phân biệt chuyển đổi kiểu thành công với quyền truy cập target |
| Dùng `publicLookup` | Tra cứu public member có thể truy cập | Kiểm tra phạm vi API public được phép |
| Consumer ở named module khác | Chạy thử với `exports`/`opens` được khai báo rõ | Xác định giới hạn JPMS thực tế, không suy diễn từ ví dụ classpath |

Nên chạy bài thử tương tác giữa thư viện và consumer trên một JDK đã ghi rõ phiên bản, trong cấu hình module giống sản phẩm; riêng ví dụ `HandleSharingDemo` có thể chạy trực tiếp trên classpath để quan sát các bước trao capability. Tránh dùng giá trị bí mật thật trong log hoặc làm kết luận dựa trên tên `Lookup` mà không xem cách nó được tạo.

### Những câu hỏi cần hỏi khi review API

- Có phương thức public nào trả `MethodHandles.Lookup` hoặc `MethodHandle` tới member nội bộ không? Tại sao consumer cần quyền đó?
- Consumer thực sự cần **gọi một hành vi** hay cần **tìm tùy ý các member khác**?
- Handle có gắn receiver bằng `bindTo` hoặc đóng gói state nội bộ nào làm tăng phạm vi dữ liệu được giữ không?
- Adapter có chỉ thay đổi kiểu hoặc giá trị đối số, hay thư viện đã thật sự định nghĩa một hợp đồng hành vi có giới hạn?
- Trong cấu hình named modules, package nào `exports`, package nào `opens` và ai là người nhận quyền?
- Nếu thu hồi tính năng hay đóng phiên làm việc, các handle đã trao trước đó sẽ hoạt động như thế nào?

## 10. Bài tập tình huống

**Bài 1 — Khác quyền lookup, cùng handle.** Lớp A có quyền với `private String secret()`; lớp B không tra cứu được private method đó bằng `MethodHandles.lookup()` của B. A trả cho B handle đã tìm trước. B có thể gọi handle không?

**Gợi ý:** Có, nếu B thỏa kiểu gọi và các điều kiện runtime của target. B không cần thực hiện lại `findVirtual`. Cần phân biệt thất bại tra cứu của B với khả năng gọi handle do A đã tạo.

**Bài 2 — Rò rỉ một handle hay một Lookup.** API `getSecretHandle()` trả handle cho một private method; `getPrivilegedLookup()` trả `Lookup` đầy đủ quyền của class sở hữu. Cái nào có thể cho consumer thêm khả năng tra cứu private field khác?

**Gợi ý:** `Lookup` có thể được dùng để tạo thêm handle trong phạm vi quyền của nó. Handle ban đầu chỉ cấp năng lực target đã chọn, dù caller có thể tạo adapter cho chính target đó.

**Bài 3 — Dùng `bindTo` có an toàn tuyệt đối không?** Thư viện trả một bound handle không còn nhận receiver. Nó có còn cho caller gọi private operation không? Cần kiểm tra thêm điều gì?

**Gợi ý:** Vẫn gọi được target trên receiver đã gắn. Cần xem target có hành vi nhạy cảm không, receiver có state gì và handle có giữ receiver sống lâu hơn mong muốn không.

**Bài 4 — `asType` có hạ quyền không?** Một private handle kiểu `(Vault)String` được chuyển thành `(Object)String`. Sau đó consumer gọi thành công bằng receiver kiểu `Object` có chứa `Vault`. Kết luận nào phù hợp?

**Gợi ý:** Adapter đã thay đổi kiểu nhìn thấy ở call site và áp chuyển đổi về `Vault`. Nó không làm private method public và không buộc consumer tìm lại private member.

**Bài 5 — Tách classpath và module.** Test trên classpath thấy `ExternalConsumer` có thể dùng `privateLookupIn` để truy cập `Vault` trong cùng unnamed module. Khi tách `Vault` sang named module và không `opens` package nội bộ cho consumer, có thể mặc định kết quả vẫn giống không?

**Gợi ý:** Không. Phải kiểm tra khả năng đọc module, điều kiện `opens`, quyền của lookup đầu vào và cấu hình triển khai thực tế.

## 11. Những nguyên tắc cần nhớ

1. **Lookup là năng lực tra cứu**, còn **MethodHandle đã tạo là năng lực gọi** một target theo kiểu cụ thể.
2. Quyền private cần để tạo handle được kiểm tra trong bước tra cứu. Một caller khác có thể gọi handle **đã được chia sẻ**, dù caller đó không tự tìm được member bằng lookup của mình.
3. `MethodHandles.lookup()` phản ánh lớp gọi phương thức này. Trả một `Lookup` giàu quyền từ thư viện có thể cho consumer cơ hội tạo thêm nhiều handle ngoài ý định ban đầu.
4. `bindTo` cố định receiver; `asType` thích nghi kiểu; các adapter không tự khôi phục kiểm tra quyền private theo caller mới.
5. `publicLookup` và JPMS có ý nghĩa với phạm vi tra cứu, nhưng **không tự thu hồi** năng lực của raw private handle mà thư viện đã xuất.
6. **Cùng unnamed module** không phải ranh giới đóng gói tương đương hai named modules có `opens` được kiểm soát; thí nghiệm cần ghi rõ môi trường.
7. API thư viện nên công khai hành vi cụ thể, giữ kín lookup/handle có quyền cao và kiểm tra các capability được trao ra ngoài như một phần hợp đồng bảo trì.

Thiết kế tốt là xác định rõ **ai cần thực hiện hành vi nào**, tạo capability đúng phạm vi và chủ động quản lý cách chia sẻ nó. Nguyên tắc này vẫn áp dụng cho `MethodHandle` và `Lookup` trên các JDK hiện đại.
