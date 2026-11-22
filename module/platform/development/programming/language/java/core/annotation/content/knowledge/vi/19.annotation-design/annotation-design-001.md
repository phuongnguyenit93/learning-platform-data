# Chọn annotation hay API tường minh theo bài toán trong Java

## 1. Câu hỏi thiết kế: mô tả metadata hay yêu cầu thực hiện hành vi?

Khi thiết kế thư viện và ứng dụng Java, có nhiều cách để kết nối một lớp hoặc phương thức với cơ chế bên ngoài. Chẳng hạn, muốn đăng ký một handler xử lý tác vụ, ta có thể viết:

```java
@Command("pay")
public String pay() {
    return "paid";
}
```

Hoặc đăng ký trực tiếp bằng API:

```java
registry.register("pay", service::pay);
```

Hai cách có thể dẫn đến hành vi cuối cùng tương tự, nhưng thể hiện **hai hợp đồng khác nhau**:

- **Annotation:** đặt thông tin mô tả (*metadata*) vào khai báo chương trình. Một compiler, annotation processor, framework hoặc bộ quét reflection phải **chủ động đọc** annotation và quyết định xử lý.
- **API tường minh (explicit API):** mã Java gọi trực tiếp một method/constructor/builder để yêu cầu một hành động hoặc tạo cấu hình. Đường thực thi và kiểu tham số thể hiện trong lời gọi Java thông thường.

Không có quy tắc “annotation luôn gọn hơn nên tốt hơn” hoặc “API tường minh luôn dễ hiểu hơn”. Lựa chọn phụ thuộc vào **thời điểm biết giá trị**, **ai sở hữu vòng đời hành vi**, **có cần khám phá tự động hay không**, **mức độ cần kiểm tra bằng compiler**, **khả năng thay đổi và debug**, và **chi phí học/duy trì framework**.

Tư duy quan trọng nhất:

> Nếu thông tin là một đặc điểm tương đối ổn định của **khai báo** và sẽ được một công cụ biết trước diễn giải, annotation là ứng viên tốt. Nếu thông tin là **đầu vào động, lựa chọn runtime, chuỗi thao tác hoặc điều khiển hành vi**, API tường minh thường phù hợp hơn.

Đây là heuristic thiết kế, không phải ranh giới tuyệt đối. Một hệ thống có thể và thường nên kết hợp cả hai.

## 2. Annotation làm được gì và không tự làm được gì?

Annotation type được khai báo bằng `@interface`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Command {
    String value();
}
```

Định nghĩa trên nói rằng:

- `@Command` có thể đặt trên khai báo method.
- `value()` chứa tên lệnh kiểu `String`.
- Với `RetentionPolicy.RUNTIME`, Java reflection có thể đọc annotation trên method.
- Bản thân `@Command` **không gọi method**, không tạo registry, không mở kết nối, không kiểm tra phân quyền và không tự chạy `pay()`.

Ví dụ:

```java
@Command("pay")
public String pay() {
    return "paid";
}
```

Nếu không có processor/framework/runtime scanner đọc `@Command` và thiết lập cơ chế dispatch, annotation vẫn chỉ là metadata.

Trong khi đó:

```java
registry.register("pay", service::pay);
```

là một **lời gọi Java bình thường**. Khi chương trình thực thi đến dòng này, `registry.register(...)` được gọi. Registry có thể lập tức lưu handler, kiểm tra trùng tên hoặc báo lỗi theo logic đã lập trình.

### Annotation không phải một lời gọi hàm

`@Command("pay")` là một annotation use theo cú pháp Java; nó không tương đương:

```java
Command("pay"); // Không phải cách “gọi annotation”.
```

Muốn kích hoạt logic dựa trên annotation, bạn phải lập trình consumer: annotation processor, reflective scanner hoặc framework có khả năng hiểu annotation ấy.

## 3. Bảng so sánh nhanh theo tiêu chí thiết kế

| Tiêu chí | Annotation | API tường minh |
|---|---|---|
| Ý nghĩa chính | Metadata gắn với khai báo | Lời gọi yêu cầu hành vi hoặc cấu hình |
| Giá trị | Thường là hằng hoặc cấu trúc annotation hợp lệ đã biết tại biên dịch | Có thể là biến, object, lambda, collection, kết quả tính toán runtime |
| Thời điểm xử lý | Source, class file hoặc runtime tùy `@Retention` và consumer | Khi code gọi API; một builder có thể được gọi lúc khởi động |
| Liên kết với khai báo | Rất gần class/method/field được mô tả | Có thể tập trung trong bootstrap/configuration code |
| Phát hiện thành phần | Hợp với processor hoặc scanner quét metadata | Thường đăng ký hoặc gọi trực tiếp |
| Kiểm tra kiểu | Compiler kiểm tra cú pháp/kiểu element; luật nghiệp vụ cần processor/framework | Compiler kiểm tra method signature và generic; luật nghiệp vụ vẫn cần API validate |
| Điều chỉnh theo môi trường | Khó nếu phải thay annotation values theo runtime | Dễ truyền giá trị từ config, người dùng, tham số lệnh |
| Luồng điều khiển | Gián tiếp: cần biết ai quét và khi nào | Tường minh hơn: tìm call site và theo đường gọi |
| Debug | Có thêm lớp discovery, retention, scan, proxy/processor | Thường đi theo stack trace và lời gọi bình thường |
| Chi phí framework | Có thể cần scanning/processor/registration | Có thể cần bootstrap/builder nhưng ít “phép màu” hơn |
| Khả năng tái sử dụng | Metadata dùng được bởi nhiều tool được thiết kế hỗ trợ | Hợp đồng method/interface linh hoạt và có thể truyền triển khai |
| Tính biểu đạt | Tốt cho nhãn, quy tắc, mapping ngắn | Tốt cho workflow, điều kiện, branching, tham số runtime |

Bảng mô tả xu hướng, không khẳng định mọi framework annotation đều quét reflection hoặc mọi API tường minh đều chạy ngay: một số API chỉ xây dựng cấu hình để áp dụng sau. Điều cần xem là **hợp đồng thực tế của consumer**.

## 4. Trường hợp nên ưu tiên annotation

Annotation có ích khi metadata là thuộc tính mang tính **khai báo và ổn định** của một phần tử.

### 4.1. Phần tử cần tự mô tả cho nhiều công cụ

Ví dụ đánh dấu một class thuộc nhóm API nội bộ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface InternalApi {
    String owner();
}

@InternalApi(owner = "platform")
class CacheInternal {
}
```

Một công cụ phân tích class file có thể đọc metadata để tạo báo cáo hoặc kiểm tra kiến trúc. Nếu việc đọc chỉ diễn ra trong khi biên dịch source, `SOURCE` cũng có thể đủ; nếu cần runtime reflection, phải chọn `RUNTIME`.

Ở đây, metadata gắn trực tiếp vào **khai báo class** và không phụ thuộc số lượng request đang xử lý.

### 4.2. Framework thực sự có cơ chế khám phá bằng annotation

Các framework DI, web routing, persistence hoặc test framework thường đã định nghĩa annotation của chúng. Khi dùng đúng framework, annotation có thể giúp khai báo ngắn gọn các quy tắc mà framework được lập trình để đọc.

Tuy vậy, sự hiện diện của `@MyRoute` tự tạo không khiến framework tự biết đến nó. Bạn phải dùng annotation framework hỗ trợ hoặc viết extension/processor tương ứng.

### 4.3. Cần kiểm tra hoặc sinh mã lúc biên dịch

Một annotation `@GenerateAdapter` có thể được annotation processor đọc từ source, kiểm tra điều kiện, rồi sinh Java source qua `Filer`. Nếu metadata chỉ dùng tại giai đoạn biên dịch, `RetentionPolicy.SOURCE` thường đủ.

Ví dụ khai báo:

```java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateAdapter {}

@GenerateAdapter
interface PaymentPort {}
```

Đây chỉ là **mảnh minh họa**, chưa có processor sinh mã. Một processor phải được cài đặt và cấu hình trong build để `@GenerateAdapter` có tác dụng.

### 4.4. Metadata ngắn, tập kiểu ổn định

Annotation phù hợp với một tập nhỏ giá trị như:

- Enum xác định mức phân loại.
- Chuỗi tên logical identifier.
- Mảng các kiểu `String`, enum hoặc nested annotation.
- Class literal `SomeType.class` để mô tả kiểu tham chiếu.

Nếu giá trị biến động liên tục theo request hoặc cần object runtime lớn, annotation không còn là nơi tự nhiên để chứa chúng.

## 5. Trường hợp nên ưu tiên API tường minh

### 5.1. Cấu hình dựa vào điều kiện runtime

Ví dụ timeout lấy từ biến môi trường, user preference hoặc hệ thống cấu hình:

```java
int timeoutMillis = Integer.parseInt(
        System.getenv().getOrDefault("PAYMENT_TIMEOUT_MS", "1500"));

client.setTimeoutMillis(timeoutMillis);
```

`setTimeoutMillis` trong ví dụ là method minh họa thuộc một client do ứng dụng định nghĩa. Giá trị chỉ biết lúc chạy nên một API nhận `int` runtime phù hợp.

Không thể thay bằng:

```java
@Timeout(milliseconds = Integer.parseInt(
        System.getenv("PAYMENT_TIMEOUT_MS")))
class PaymentClient {}
```

Đoạn trên **không hợp lệ** trong Java annotation: element `int` phải nhận constant expression, còn lời gọi method để đọc environment là phép tính runtime.

Một số framework cho phép **chuỗi biểu thức** trong annotation như `@Value("\${...}")` rồi tự phân giải lúc chạy; đó là **cơ chế riêng của framework**, không thay đổi quy tắc Java rằng annotation element chứa một chuỗi hợp lệ tại biên dịch. Người thiết kế phải cân nhắc độ phức tạp và khả năng kiểm tra của cơ chế diễn giải chuỗi này.

### 5.2. Hành vi là chuỗi bước có nhánh hoặc callback

Ví dụ:

```java
if (account.isEligible()) {
    workflow.transfer(account, amount);
} else {
    workflow.reject(account);
}
```

Đây là mã minh họa trong ứng dụng có `account`, `workflow` và `amount` đã được khai báo. Luồng quyết định, trạng thái object và việc gọi method là nhiệm vụ phù hợp với Java code. Dùng annotation để mô tả toàn bộ chuỗi thao tác thường tạo DSL ngầm khó debug.

### 5.3. Cần truyền lambda, object, collection hoặc trạng thái

Annotation element chỉ hỗ trợ tập kiểu giới hạn của Java: kiểu nguyên thủy, `String`, `Class`, enum, annotation và mảng một chiều của chúng. Nó **không** nhận `Supplier<T>`, `Predicate<T>`, `Map`, `List` hay instance object do `new` tạo.

API tường minh có thể dùng:

```java
registry.register(
        "pay",
        () -> service.pay(currentUserId));

Map<String, String> options = Map.of(
        "region", "ap-southeast-1",
        "mode", "safe");
```

Đây là đoạn minh họa cần `registry`, `service` và `currentUserId` ở scope hiện tại. Sức mạnh của API là nhận các object/closure được tính ở runtime, được kiểm tra kiểu bằng generic và có thể validate theo logic nghiệp vụ.

### 5.4. Cần kiểm soát chặt thời điểm và thứ tự thực thi

Nếu hành vi phải xảy ra **chính xác tại một bước** trong bootstrap, explicit API làm vị trí ấy dễ tìm:

```java
registry.register("pay", service::pay);
registry.validate();
server.start();
```

Đây là pseudocode Java theo một API giả định. Nó minh họa thứ tự thiết lập → kiểm tra → khởi động; không phải chương trình độc lập.

Với annotation, thứ tự discovery/registration có thể do framework điều khiển và cần học thêm cơ chế scan, sorting, lifecycle hooks và ưu tiên cấu hình.

## 6. Ba câu hỏi quyết định trước khi viết `@interface`

Trước khi tạo annotation type mới, trả lời:

**Câu hỏi A — Giá trị được biết khi nào?**

- Cố định khi biên dịch và gắn với class/method: nghiêng về annotation.
- Chỉ biết khi ứng dụng chạy hoặc thay đổi theo người dùng/request: nghiêng về API nhận tham số runtime.

**Câu hỏi B — Ai sẽ đọc và thực thi ý nghĩa của metadata?**

- Đã có framework hoặc processor hỗ trợ kiểu annotation ấy: annotation khả thi.
- Chưa có consumer cụ thể và cần tự xây toàn bộ scanner chỉ để tiết kiệm vài dòng đăng ký: cân nhắc API trước.
- Cần processor để phát hiện lỗi sớm/sinh mã: annotation có lợi khi build pipeline được kiểm soát.

**Câu hỏi C — Điều gì phải minh bạch với người bảo trì?**

- Người đọc code cần thấy nhãn/ngữ nghĩa ngay tại method: annotation tốt.
- Người đọc cần lần theo việc một handler được thêm, thay thế hoặc loại bỏ theo điều kiện: explicit API tốt.
- Cần cả metadata lẫn chủ động cấu hình registry: kết hợp annotation và API với ranh giới trách nhiệm rõ ràng.

Khi chưa chắc, một **API nhỏ với interface rõ ràng** thường là điểm xuất phát có thể kiểm thử dễ hơn; chỉ thêm annotation khi lợi ích declarative discovery thật sự bù được chi phí consumer và lifecycle. Đây là khuyến nghị thiết kế, không phải quy định của ngôn ngữ.

## 7. Ví dụ Java 17+ hoàn chỉnh: cùng một tác vụ bằng hai cách

Ví dụ dùng một **registry đơn giản** cho các action không tham số, trả `String`.

- Đường **annotation**: `@Action("pay")`, `@Action("audit")` trên method; scanner runtime dùng reflection để đăng ký.
- Đường **API tường minh**: gọi `register("refund", supplier)` trực tiếp với một lambda dùng dữ liệu runtime.

Mọi class ở trong **một file `AnnotationOrApiDemo.java`**. Không cần thư viện ngoài.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Supplier;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Action {
    String value();
}

class BillingActions {
    @Action("pay")
    public String pay() {
        return "paid";
    }

    @Action("audit")
    public String audit() {
        return "checked";
    }
}

class Registry {
    private final Map<String, Supplier<String>> actions =
            new TreeMap<>();

    public void register(String name, Supplier<String> callback) {
        if (name == null || name.isBlank() || callback == null) {
            throw new IllegalArgumentException("Invalid registration");
        }
        if (actions.putIfAbsent(name, callback) != null) {
            throw new IllegalArgumentException("Duplicate: " + name);
        }
    }

    public void registerAnnotated(Object instance) {
        for (Method method :
                instance.getClass().getDeclaredMethods()) {

            Action action = method.getAnnotation(Action.class);
            if (action == null) {
                continue;
            }

            if (method.getParameterCount() != 0 ||
                    method.getReturnType() != String.class) {
                throw new IllegalArgumentException(
                        "Expected zero-arg String method: "
                        + method.getName());
            }

            register(action.value(), () -> {
                try {
                    return (String) method.invoke(instance);
                } catch (IllegalAccessException |
                         InvocationTargetException ex) {
                    throw new IllegalStateException(ex);
                }
            });
        }
    }

    public String invoke(String name) {
        Supplier<String> callback = actions.get(name);
        if (callback == null) {
            throw new IllegalArgumentException("Unknown: " + name);
        }
        return callback.get();
    }

    public String names() {
        return actions.keySet().toString();
    }
}

public class AnnotationOrApiDemo {
    public static void main(String[] args) {
        Registry annotated = new Registry();
        annotated.registerAnnotated(new BillingActions());

        System.out.println("annotation names=" + annotated.names());
        System.out.println("annotation pay="
                + annotated.invoke("pay"));

        String orderId = args.length == 0 ? "42" : args[0];
        Registry explicit = new Registry();
        explicit.register("refund", () -> "refunded:" + orderId);

        System.out.println("api names=" + explicit.names());
        System.out.println("api refund="
                + explicit.invoke("refund"));
    }
}
```

Lưu file, biên dịch và chạy:

```bash
javac AnnotationOrApiDemo.java
java AnnotationOrApiDemo
```

Kết quả stdout khi **không truyền command-line argument**:

```text
annotation names=[audit, pay]
annotation pay=paid
api names=[refund]
api refund=refunded:42
```

**Giải thích kết quả:**

1. `@Action` có `RetentionPolicy.RUNTIME` và `ElementType.METHOD` nên scanner có thể đọc metadata trên method.
2. `registerAnnotated(new BillingActions())` tìm các method được gắn `@Action`, kiểm tra signature và đăng ký callback để gọi sau.
3. `TreeMap` giúp tập tên được hiển thị theo thứ tự `audit, pay`, **không phụ thuộc thứ tự trả về của `getDeclaredMethods()`**.
4. `invoke("pay")` gọi handler tương ứng. Annotation **không tự gọi method**; phần code trong `Registry` thực hiện việc đó.
5. API `register("refund", () -> "refunded:" + orderId)` nhận closure với `orderId` được tính khi chương trình chạy.
6. Nếu chạy `java AnnotationOrApiDemo 99`, dòng cuối trở thành `api refund=refunded:99` mà không sửa hoặc biên dịch lại annotation nào.

Ví dụ chủ ý chỉ cho phép **public, zero-argument method trả `String`** trong `BillingActions`. Trong framework tổng quát, còn phải xử lý khả năng truy cập, proxy, inheritance, tham số, async, duplicate commands và bảo mật. Không tự bỏ kiểm tra method signature rồi tin rằng annotation làm code an toàn.

## 8. Phân tích quyết định từ ví dụ

### Vì sao `@Action` hợp lý?

Giả sử module chứa nhiều handler do các nhóm khác nhau phát triển và framework có **scanner chuẩn**. Annotating ngay trên từng method giúp:

- Metadata nằm gần logic được mô tả.
- Framework có thể tự tìm handler không cần từng module sửa một file registry trung tâm.
- Công cụ build/test có thể quét để phát hiện trùng tên, thiếu signature hoặc metadata sai.
- Khi tên lệnh là đặc tính ổn định của method, cú pháp `@Action("pay")` dễ đọc.

Chi phí phải trả:

- Cần code `registerAnnotated` và một cơ chế xác định phạm vi các class được scan.
- Sai `@Retention`, `@Target` hoặc classloader có thể làm framework không thấy annotation.
- Scanner có thể gặp lỗi runtime nếu signature/visibility chỉ được kiểm tra lúc khởi động.
- Cần tài liệu về thời điểm scanning và cách xử lý trùng tên.

### Vì sao `register(...)` hợp lý?

Ví dụ refund dùng `orderId` từ command-line argument. Đây là dữ liệu runtime, không thể đưa trực tiếp thành annotation element theo quy tắc Java.

`register("refund", callback)` cho phép:

- Dùng closure/generic interface linh hoạt thay vì một tập kiểu annotation element hạn chế.
- Biết chính xác **khi nào** handler được thêm vào registry.
- Thay đổi callback theo môi trường, feature flag hoặc người dùng.
- Test registration bằng cách cung cấp `Supplier<String>` giả lập.

Chi phí phải trả:

- Cần một chỗ bootstrap gọi `register`.
- Nếu có rất nhiều handler và mỗi handler phải khai báo lặp lại tên, code đăng ký có thể dài và dễ quên.
- Khi gọi API theo điều kiện, khó thấy toàn bộ registry chỉ từ khai báo method; cần kiểm tra bootstrap.

Hai cách không có sự hơn kém tuyệt đối. **Một annotation giảm công việc khai báo ở call site bằng cách chuyển trách nhiệm sang scanner**, còn **API tường minh giữ trách nhiệm đăng ký ngay trong code gọi**.

## 9. Kết hợp annotation với API: ranh giới rõ ràng

Một kiến trúc thực tế thường dùng cả hai:

1. Annotation mô tả **khả năng tĩnh** của một class/method.
2. Processor hoặc scanner đọc metadata và tạo **mô hình descriptor**.
3. API tường minh nhận descriptor/cấu hình runtime để **kích hoạt, giới hạn hoặc đăng ký** hành vi.
4. Người vận hành có thể override vài tham số bằng configuration object mà không sửa annotation.

Sơ đồ khái niệm:

```text
Mã nguồn
  @Action("pay") trên method
           │
           ▼
Scanner hoặc annotation processor
           │
           ▼
Danh sách action descriptors
           │
Runtime config: enabled, timeout, region
           │
           ▼
Registry.register(descriptor, handler, options)
           │
           ▼
Dispatch khi có request
```

Ở đây annotation không cần chứa timeout lấy từ database hoặc feature flag động. API tường minh không phải lặp lại mọi nhãn trên method vì scanner đã xây danh sách descriptor.

### Không tạo hai nguồn sự thật mâu thuẫn

Nếu cùng một command name vừa ở `@Action("pay")`, vừa ở file cấu hình, vừa ở lời gọi `register("checkout", ...)`, cần quy định rõ nguồn nào có quyền ưu tiên hoặc validate rằng chúng nhất quán.

Một thiết kế dễ duy trì có thể là:

- Annotation định nghĩa **ID mặc định/khả năng hỗ trợ**.
- Registry runtime quyết định **handler nào được bật**.
- Các tùy chọn động ở `ActionOptions`/config object.
- Khi trùng ID, hệ thống báo lỗi thay vì âm thầm ghi đè.
- Có test kiểm tra descriptor đọc từ annotation và cấu hình được áp dụng đúng.

Nếu không xác định trách nhiệm, việc kết hợp có thể tạo chi phí debug lớn hơn cả hai cách riêng.

## 10. Tính an toàn kiểu và thời điểm phát hiện lỗi

Một số người cho rằng annotation luôn “an toàn kiểu”, còn API mới báo lỗi khi chạy. Nhận định ấy không chính xác.

Compiler Java kiểm tra annotation element:

```java
@interface Retry {
    int attempts();
}

@Retry(attempts = 3)
class Worker {}
```

Nhưng compiler bình thường **không tự biết** rằng `attempts` phải nằm trong khoảng 1–5. Nếu không có annotation processor kiểm tra ràng buộc nghiệp vụ, `@Retry(attempts = 999)` vẫn hợp lệ về kiểu.

Với API:

```java
config.setAttempts(3);
```

Compiler kiểm tra method có tồn tại và tham số đúng kiểu, còn `setAttempts` có thể thực hiện validation ở runtime. Một builder có thể giới hạn state và dùng các enum/records/generics để thể hiện cấu hình rõ hơn.

| Kiểu lỗi | Annotation | API tường minh |
|---|---|---|
| Sai kiểu Java cơ bản | Compiler thường bắt được | Compiler thường bắt được |
| Sai tên element/method | Compiler bắt được | Compiler bắt được |
| Vi phạm điều kiện nghiệp vụ (vd: giới hạn timeout) | Cần processor hoặc consumer kiểm tra | Cần code validation hoặc kiểu biểu diễn chặt |
| Annotation không được framework quét | Có thể chỉ phát hiện khi build/startup/runtime | Lời gọi trực tiếp không phụ thuộc quét nhưng vẫn có thể đăng ký sai |
| Tham số phụ thuộc environment | Thường cần giải pháp diễn giải riêng của framework | Truyền trực tiếp giá trị runtime |
| Logic chuyển trạng thái phức tạp | Metadata thường không đủ để diễn đạt | Methods/interfaces/state machines phù hợp hơn |

**Kết luận:** Đừng dùng annotation chỉ để mang tiếng “compile-time safety”. Nếu mục tiêu là bắt lỗi nghiệp vụ **trong build**, cần một processor hoặc cơ chế phân tích tĩnh thực sự chạy được. Nếu mục tiêu là runtime safety, cần validate trên cả hai con đường.

## 11. Phạm vi annotation: kiểu giá trị, `@Target`, `@Retention`

### 11.1. Giới hạn kiểu element

Annotation element chỉ cho phép kiểu nguyên thủy, `String`, `Class` hợp lệ, enum, annotation và mảng một chiều của chúng.

Được phép:

```java
enum Mode { SAFE, FAST }

@interface Policy {
    String name();
    Mode mode() default Mode.SAFE;
    Class<?> handler();
    String[] tags() default {};
}
```

Không được dùng trực tiếp làm element:

```java
import java.util.List;

@interface BadPolicy {
    List<String> tags(); // Sai: List không phải annotation element type.
    Runnable action();   // Sai: interface Runnable không thuộc tập được phép.
    Object state();      // Sai: Object không thuộc tập được phép.
}
```

Các đoạn là minh họa loại type; `BadPolicy` cố ý không biên dịch. Trong API tường minh, `List<String>`, `Runnable` hoặc đối tượng trạng thái lại là các tham số hoàn toàn hợp lệ.

### 11.2. Hằng tại thời điểm biên dịch

Các element nguyên thủy/chuỗi của annotation được cung cấp bằng constant expression phù hợp. Ví dụ:

```java
static final int DEFAULT_RETRIES = 3;

@Retry(attempts = DEFAULT_RETRIES)
class InvoiceTask {}
```

Đoạn này cần `DEFAULT_RETRIES` ở vị trí khai báo có thể truy cập được từ `InvoiceTask` và annotation `Retry` đã tồn tại; đây là minh họa khái niệm.

Ngược lại, `@Retry(attempts = loadRetries())` không hợp lệ khi `loadRetries()` là lời gọi method runtime.

### 11.3. Đích và vòng đời

`@Target` quyết định annotation được đặt ở đâu, ví dụ `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `PACKAGE` hoặc `TYPE_USE`. `@Retention` quyết định thông tin được giữ tới mức nào:

- `SOURCE`: phục vụ xử lý source/biên dịch; không được giữ trong class file.
- `CLASS`: metadata có trong class file nhưng không hiển thị qua reflection chuẩn.
- `RUNTIME`: metadata có thể truy cập qua reflection thông thường.

Nếu không khai báo `@Retention`, Java mặc định là `CLASS`. Đặt `RUNTIME` khi consumer thực sự cần runtime reflection, không phải như một cách “kích hoạt tính năng” chung.

### 11.4. Khả năng dùng trên nhiều môi trường

Annotation là một phần của bytecode/artifact khi retention yêu cầu giữ. Việc thay đổi annotation values có thể đòi hỏi biên dịch lại class được chú thích. Nếu metadata phụ thuộc tenant, region hoặc credentials thay đổi hằng ngày, tách các giá trị ấy sang cấu hình runtime/API thay vì gắn cố định vào source.

## 12. Tiêu chí về discoverability và khả năng debug

Annotation giúp **khám phá theo khai báo**: muốn biết vì sao method đăng ký là command, tìm `@Action` ngay cạnh method. Nhưng để biết **khi nào nó được kích hoạt**, cần hiểu scanner/framework.

API tường minh giúp **lần theo luồng điều khiển**: IDE có thể tìm call sites của `register`, debugger có thể dừng ở registration call hoặc method body.

Hãy hỏi khi chọn cách thiết kế:

- Consumer có đọc annotation type này chưa, hay ta phải tự tạo toàn bộ scanner?
- Phạm vi quét là package nào? Có phụ thuộc classpath, module, proxy, generated classes hay class loaders không?
- Có cần thứ tự đăng ký ổn định hay không?
- Điều gì xảy ra khi hai method cùng `@Action("pay")`?
- Khi annotation bị gỡ bỏ, build/test có phát hiện rằng handler bị mất không?
- Một handler có thể được kích hoạt và hủy đăng ký ở runtime không?
- Có test độc lập cho scanner, validation, và actual dispatch hay không?

Nếu hệ thống nhỏ, chỉ vài registrations cố định, một danh sách lời gọi API có thể dễ kiểm soát hơn một scanner mới. Nếu quy mô lớn và framework chuẩn hỗ trợ annotation có lifecycle rõ ràng, annotation có thể giảm boilerplate đáng kể.

**Đừng đánh đồng ít dòng code tại nơi sử dụng với tổng chi phí hệ thống thấp.** Hãy tính cả phần infrastructure, test, lỗi cấu hình và đường vận hành.

## 13. Những anti-pattern cần tránh

### 13.1. “Annotation thần kỳ”: gắn vào là tự chạy

Sai lầm:

```java
@Cacheable
String lookup(String key) {
    return databaseRead(key);
}
```

Mảnh này chỉ có ý nghĩa caching nếu có framework/proxy/aspect/tool đã được cấu hình để hiểu `@Cacheable`; tên annotation tự đặt không làm Java tự tạo cache.

Hướng tốt hơn: dùng annotation framework hỗ trợ, hoặc API cache trực tiếp:

```java
String value = cache.getOrCompute(key, () -> databaseRead(key));
```

Đoạn minh họa cần các biến/method có sẵn; điểm chính là hành vi cache được gọi tường minh.

### 13.2. Đẩy dữ liệu runtime vào string annotation

Ví dụ `@Schedule(expression = "\${ENV_RATE}")` không tự đọc biến môi trường theo ngôn ngữ Java. Framework có thể diễn giải chuỗi ấy, nhưng khi xây hệ thống riêng, bạn đang thêm một *mini language*, parser, error handling và quy tắc escape cần bảo trì.

Nếu bản chất là runtime configuration, cân nhắc nhận `ScheduleOptions` qua API hoặc file cấu hình có schema.

### 13.3. Một annotation ôm toàn bộ workflow

`@Payment(policy = "...", retry = "...", authorization = "...")` có thể dần biến thành chuỗi cấu hình lớn, khó biểu đạt trạng thái và xử lý exception.

Nếu logic đòi hỏi nhánh, retry backoff động, cancellation hoặc transaction orchestration, hãy dùng interface, strategy object hoặc workflow engine tường minh. Annotation có thể giữ một nhãn chọn strategy mà không cần mô tả mọi bước.

### 13.4. Gắn quá nhiều annotation nhưng không có mô hình ưu tiên

Một method có nhiều annotation từ nhiều framework dễ tạo xung đột: annotation nào thắng, thứ tự interceptors ra sao, hiệu lực trên proxy và method override thế nào? Cần tài liệu và test integration, không chỉ thêm một annotation nữa.

### 13.5. Dùng reflection scanner khi chỉ cần vài dòng đăng ký

Reflection có chi phí học và vận hành. Nếu chỉ có ba handlers và không cần plugin discovery, `registry.register(...)` có thể giải quyết nhanh và rõ hơn.

### 13.6. Thay API công khai bằng annotation chỉ để “trông framework hơn”

Annotation không có generics linh hoạt như API, không thể cung cấp object/lambda và không diễn đạt trực tiếp contract của một service interface. Không nên bỏ interfaces hoặc phương thức vốn phù hợp với tương tác runtime chỉ để người dùng viết `@Something`.

### 13.7. Nhét bí mật vào annotation values

Annotation `RUNTIME` được giữ trong artifact và có thể đọc bằng reflection; `CLASS` vẫn có thể đọc từ bytecode. **Không lưu mật khẩu, token hoặc khóa riêng** trong annotation chỉ vì code ngắn gọn.

## 14. Ví dụ tình huống thực tế và lựa chọn phù hợp

| Bài toán | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Đánh dấu class là internal API để lint/CI kiểm tra | Annotation | Metadata tĩnh gắn với type |
| Sinh mapper từ interface ở compile time | Annotation + processor | Tự động hóa khai báo ổn định |
| Đăng ký 3 command cố định của ứng dụng nhỏ | Explicit API | Tránh xây scanner không cần thiết |
| Framework web đã hỗ trợ `@GetMapping`/`@Route` | Annotation theo contract framework | Khai báo gần handler, framework xử lý |
| Timeout thay đổi theo tenant và user | API/config runtime | Giá trị động |
| Workflow thanh toán có bước điều kiện/rollback | API/objects/services | Luồng hành vi phức tạp |
| Plugin tự khám phá class do bên thứ ba cung cấp | Annotation hoặc interface + discovery | Cần chọn contract và cơ chế scan cụ thể |
| Dùng callback/lambda runtime | Explicit API | Annotation không nhận functional object |
| Build tool kiểm tra kiến trúc package | Package annotation + tool hoặc quy tắc build rõ ràng | Metadata ở cấp package, cần consumer |
| Một flag bật/tắt ở runtime | API/config/feature flag service | Không nên recompilation để thay đổi |
| Một test framework đã định nghĩa `@Test` | Annotation của framework | Framework biết cách tìm và chạy tests |
| Metadata cố định nhưng handler cho phép bật/tắt động | Kết hợp annotation + API | Để khai báo và activation có trách nhiệm riêng |

Đây là các khuyến nghị có điều kiện: trước tiên hãy xét **framework thật đang dùng**, vòng đời ứng dụng và khả năng kiểm thử.

### Bài toán plugin: annotation hay service interface?

Nếu plugin cần công bố nhiều implementations, đôi khi `ServiceLoader` với một interface và provider configuration cung cấp contract tường minh hơn là tự tạo scanner classpath. Ngược lại, nếu framework đã có annotation discovery hiệu quả, metadata có thể phù hợp.

Không có lựa chọn nào tự động phát hiện plugin trong mọi JAR chỉ vì annotation tồn tại. Thiết kế cần chỉ rõ **cơ chế discovery**, ranh giới class loader và cách xử lý lỗi.

## 15. Checklist ra quyết định theo từng bước

Trước khi thêm `@interface` mới:

1. **Mô tả nhu cầu bằng một câu:** cần đánh dấu metadata hay thực thi/cấu hình hành vi?
2. **Liệt kê consumer cụ thể:** compiler, processor, bytecode scanner, reflection framework hay người gọi API?
3. **Xác định thời điểm biết giá trị:** compile time, lúc khởi động, theo mỗi request hay theo user?
4. **Kiểm tra loại dữ liệu:** chuỗi/enum/class literal/hằng, hay object/lambda/list/map/runtime callback?
5. **Xác định contract vòng đời:** ai scan, khi nào scan, có hỗ trợ disable/re-register không?
6. **Đánh giá error handling:** lỗi sẽ được phát hiện trong javac, lúc bootstrap hay khi request thực thi?
7. **Đánh giá khả năng test:** có thể test kết quả annotation processing hoặc registry trực tiếp không?
8. **Cân nhắc người dùng API:** thích khai báo tại class/method hay tập trung startup config?
9. **Ưu tiên nguồn sự thật duy nhất:** nếu kết hợp, chỉ định metadata và runtime override thuộc về bên nào.
10. **Đo độ phức tạp toàn hệ thống:** không chỉ đếm số dòng annotation.
11. **Xem xét tương thích khi nâng phiên bản:** đổi annotation schema, retention/target hoặc API signature tác động ra sao?
12. **Viết một thử nghiệm nhỏ:** chọn đúng framework/tool và test cả đường thành công lẫn sai cấu hình.

Một cây quyết định ngắn:

```text
Thông tin gắn ổn định với khai báo?
        │
      Không ─────────────► Ưu tiên explicit API/runtime config
        │ Có
        ▼
Đã có consumer hiểu annotation hoặc thật sự cần processor?
        │
      Không ─────────────► Cân nhắc explicit registration/interface
        │ Có
        ▼
Giá trị có thuộc tập kiểu annotation hợp lệ và là metadata tĩnh?
        │
      Không ─────────────► Tách phần động sang API/config
        │ Có
        ▼
Annotation là lựa chọn hợp lý
        │
        ▼
Thiết kế @Target, @Retention, validation,
discovery, lỗi, test và fallback rõ ràng
```

## 16. Bài tập tự kiểm tra và giải thích

Xét các yêu cầu sau. Hãy chọn **annotation**, **API tường minh**, hoặc **kết hợp**.

**Tình huống A:** Một thư viện nội bộ muốn đánh dấu những class không được phụ thuộc vào module giao diện. Công cụ CI đã có khả năng đọc annotation trong `.class`.

**Tình huống B:** Thời gian timeout phụ thuộc region và được điều chỉnh từ hệ thống quản trị lúc runtime.

**Tình huống C:** Một hệ thống DI đã có annotation để khai báo component; ứng dụng cần chọn cài đặt service theo feature flag.

**Tình huống D:** Một công cụ build sinh adapter từ những interface được gắn nhãn, không cần metadata ấy trong ứng dụng sau biên dịch.

**Tình huống E:** Một thư viện cần cho người dùng truyền `Predicate<Request>` để quyết định có chấp nhận request hay không.

**Tình huống F:** Ba handler cố định cần được đăng ký khi ứng dụng khởi động; hệ thống chưa có scanner hoặc processor.

**Tình huống G:** Muốn annotation `@Retry(attempts = 3)` luôn có giá trị từ 1 đến 5, và lỗi phải được báo ngay trong build.

**Tình huống H:** Muốn thay thứ tự các bước trong workflow theo yêu cầu người dùng vào mỗi request.

**Đáp án gợi ý:**

- **A — Annotation:** metadata ổn định; chọn retention ít nhất đủ để công cụ CI đọc bytecode (ví dụ `CLASS`) và bảo đảm tool thật sự áp dụng kiểm tra.
- **B — API/config runtime:** giá trị thay đổi trong khi ứng dụng chạy, không nên đóng cứng vào annotation element.
- **C — Kết hợp:** dùng annotation để đánh dấu capability/service cho DI; dùng API/config/feature flag để điều khiển lựa chọn runtime theo contract framework.
- **D — Annotation + processor:** metadata dùng lúc biên dịch, `SOURCE` có thể đủ nếu processor xử lý source phù hợp.
- **E — API tường minh:** annotation element không nhận `Predicate<Request>`; dùng functional interface trong Java.
- **F — API tường minh:** một registry được gọi trực tiếp đơn giản hơn việc tự xây scanner chỉ cho ba handlers.
- **G — Annotation + annotation processor kiểm tra:** Java compiler chỉ kiểm tra kiểu `int`; cần processor chạy trong build để kiểm tra miền 1–5 và dùng `Messager` báo lỗi.
- **H — API/services/workflow object:** thứ tự và trạng thái động là hành vi runtime, không thích hợp mô tả toàn bộ bằng các hằng trong annotation.

### Hai câu hỏi bổ sung

1. `@Action("pay")` có tự tạo route hay command không? **Không.** Cần consumer/framework.
2. Đổi annotation từ `SOURCE` sang `RUNTIME` có tự khiến một framework nhận biết annotation mới không? **Không.** Retention chỉ làm metadata có thể quan sát được qua reflection; framework vẫn phải biết cách đọc và xử lý.

## 17. Tóm tắt và tài liệu tham khảo

**Chọn annotation khi:**

- Metadata tương đối tĩnh và thật sự gắn với khai báo Java.
- Có consumer cụ thể cần đọc metadata ấy.
- Muốn framework, compiler hoặc processor khám phá/cấu hình/xác minh một quy tắc lặp lại.
- Kiểu giá trị và vòng đời phù hợp giới hạn của annotation.

**Chọn API tường minh khi:**

- Hành vi hoặc cấu hình thay đổi lúc chạy.
- Cần truyền object, generic, collection, lambda/callback hoặc điều kiện động.
- Cần biểu diễn quy trình nhiều bước, trạng thái và thứ tự thực thi.
- Muốn dễ truy vết call site, kiểm soát lỗi và viết unit test trực tiếp.
- Quy mô bài toán không biện minh cho chi phí một scanner/processor mới.

**Kết hợp khi:** annotation biểu diễn capability/metadata tĩnh, còn API nhận config động và kích hoạt hành vi qua một hợp đồng rõ ràng.

Các tài liệu Java SE 17 nên xem khi tự thiết kế annotation:

- [Java Language Specification, Chương 9 — Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): cú pháp, kiểu element hợp lệ và giới hạn giá trị.
- [`Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html) và [`Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html): vòng đời và đích áp dụng.
- [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): tra cứu annotation lúc chạy.
- [`Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): hợp đồng annotation processing khi biên dịch.

**Kết luận:** Annotation là một **ngôn ngữ metadata gắn trên chương trình**; API tường minh là một **hợp đồng tương tác bằng Java code**. Quyết định tốt xuất phát từ nhu cầu thực thi và bên tiêu thụ, không phải từ việc cú pháp nào ngắn hơn hoặc trông hiện đại hơn.