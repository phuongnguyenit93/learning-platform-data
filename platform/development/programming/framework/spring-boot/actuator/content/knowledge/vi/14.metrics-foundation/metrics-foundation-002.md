# Vai trò của Meter, Meter.Id, MeterRegistry và CompositeMeterRegistry

## 1. Bắt đầu từ một phép đo cụ thể

Giả sử ứng dụng cần đếm số đơn hàng đã xử lý, tách theo kênh tiếp nhận và kết quả. Mỗi lần hoàn tất một đơn, mã nghiệp vụ cần ghi nhận thêm một lần; dữ liệu đo sau đó có thể được đọc trong ứng dụng hoặc đưa tới hệ thống giám sát.

Micrometer phân chia công việc này thành bốn khái niệm. **`Meter` là công cụ đo; `Meter.Id` mô tả danh tính và siêu dữ liệu của công cụ; `MeterRegistry` tạo, giữ và tìm các công cụ đo; `CompositeMeterRegistry` phối hợp nhiều registry để một lần ghi được chuyển tới nhiều nơi.** Spring Boot Actuator tích hợp và đưa những phép đo này vào khả năng quan sát của ứng dụng.

| Thành phần | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| `Meter` | Đang đo điều gì và đọc/ghi bằng giao diện nào? | `Counter` đếm số đơn hoàn tất |
| `Meter.Id` | Công cụ đo này được nhận diện như thế nào? | Tên `shop.orders`, tags `channel=web`, `result=success` |
| `MeterRegistry` | Lấy hoặc đăng ký công cụ đo ở đâu? | `registry.counter(...)` trả về counter tương ứng |
| `CompositeMeterRegistry` | Một lần ghi cần được chuyển tới những registry nào? | Chuyển `increment()` tới hai registry con |

Trong bài này, “meter” chỉ đối tượng công cụ đo; “phép đo” chỉ giá trị hoặc thống kê nó cung cấp; “chuỗi thời gian” chỉ dữ liệu mà hệ thống giám sát lưu qua nhiều thời điểm. Không phải cứ tạo một meter là đã có một cơ sở dữ liệu lịch sử.

Ví dụ và các chi tiết triển khai được đối chiếu với **Micrometer 1.13.0**, là dòng phiên bản tương ứng Spring Boot 3.3. Ví dụ độc lập dùng Java 17+; khi làm trong dự án Boot, nên để Boot quản lý phiên bản Micrometer tương thích.

## 2. Meter: giao diện chung của công cụ đo

`Meter` là giao diện nền tảng cho một tập phép đo liên quan. Các loại như `Counter`, `Timer`, `Gauge`, `DistributionSummary` và `LongTaskTimer` có ý nghĩa đo khác nhau, không phải những cách đặt tên khác nhau cho một bộ đếm.

- `Counter` ghi nhận lượng tăng tích lũy, chẳng hạn số đơn đã xử lý.
- `Timer` ghi nhận số lần và thời lượng của các thao tác.
- `Gauge` đọc một giá trị hiện tại, chẳng hạn số công việc đang chờ.
- `DistributionSummary` quan sát độ lớn của các mẫu, chẳng hạn kích thước thông điệp.

Ở cấp `Meter`, hai thao tác quan trọng là `getId()` để đọc định danh và `measure()` để duyệt các thống kê dưới dạng `Measurement`. Khi ghi dữ liệu, dùng giao diện đúng loại: `Counter.increment()`, `Timer.record(...)` hoặc cơ chế quan sát của gauge. Không có một phương thức `Meter.increment()` chung cho mọi loại.

```java
Counter completed = registry.counter(
    "shop.orders", "channel", "web", "result", "success");

completed.increment();

Meter meter = completed;
Meter.Id id = meter.getId();

for (var measurement : meter.measure()) {
    System.out.println(
        measurement.getStatistic() + "=" + measurement.getValue());
}
```

Đoạn trên minh họa cách dùng API trong một phương thức đã có biến `registry`; nó không phải chương trình độc lập. Một counter thường cung cấp thống kê `COUNT`. Với timer có nhiều thống kê và tùy cấu hình có thêm histogram, một meter có thể trở thành nhiều chuỗi thời gian ở hệ thống đích. Vì vậy **số meter trong registry không đồng nghĩa số chuỗi thời gian được xuất**. [Khái niệm Meter của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

## 3. Meter.Id: danh tính khác với giá trị đo

### 3.1. Có gì trong một định danh?

`Meter.Id` giữ tên, tags, loại meter và siêu dữ liệu như mô tả, đơn vị cơ sở. Ví dụ:

```text
name        = shop.orders
tags        = channel=web, result=success
type        = COUNTER
baseUnit    = orders
description = Completed orders
```

| Thuộc tính | Vai trò |
| --- | --- |
| `name` | Tên khái niệm đang đo, chẳng hạn `shop.orders` |
| `tags` | Các chiều phân loại dưới dạng cặp khóa–giá trị |
| `type` | Loại công cụ đo như `COUNTER`, `TIMER`, `GAUGE` |
| `baseUnit` | Đơn vị giúp diễn giải lượng đo; không phải giá trị đếm |
| `description` | Mô tả ý nghĩa để người vận hành hiểu metric |

Giá trị hiện tại, chẳng hạn `3.0`, thuộc trạng thái/phép đo của counter, không nằm trong `Meter.Id`. Vì thế counter tăng từ 2 lên 3 không tạo một ID mới.

### 3.2. Tên và tags quyết định danh tính

Trong Micrometer 1.13, `Meter.Id.equals()` và `hashCode()` dựa trên **tên và tập tags đã được chuẩn hóa**. Loại, mô tả và đơn vị không tham gia phép so sánh này. Đây là lý do cần phân biệt “có trong siêu dữ liệu” và “tham gia nhận diện”. [Mã nguồn Meter.Id 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/Meter.java).

| Tên và tags | Quan hệ danh tính |
| --- | --- |
| `shop.orders{channel=web,result=success}` và cùng các cặp tags nhưng viết theo thứ tự ngược lại | Cùng danh tính |
| `shop.orders{channel=web,result=success}` và `shop.orders{channel=web,result=failure}` | Khác danh tính |
| `shop.orders{channel=web}` và `shop.orders{channel=web,result=success}` | Khác danh tính |
| Cùng tên và tags, chỉ đổi mô tả/đơn vị | Không tạo danh tính mới |

Tags là các cặp khóa–giá trị, không phải một danh sách vị trí. Nên cấp mỗi khóa đúng một giá trị rõ ràng; không dùng khóa lặp để diễn đạt nhiều giá trị đồng thời.

**Loại không nằm trong `equals()` không có nghĩa được đăng ký Counter và Timer chung một ID.** Registry kiểm tra loại meter đã đăng ký và có thể ném `IllegalArgumentException` khi đăng ký lại bằng loại không tương thích. Muốn đo thời lượng của đơn hàng, hãy dùng một tên biểu đạt thời lượng riêng, thay vì cố thay loại cho counter đang có.

### 3.3. Id có tính bất biến

Những phương thức như `withName(...)` và `withTag(...)` tạo một đối tượng ID mới; chúng không đổi meter đã đăng ký:

```java
Meter.Id original = completed.getId();
Meter.Id renamed = original.withName("shop.orders.renamed");

// original vẫn mang tên shop.orders.
// completed không bị đổi tên trong registry.
// renamed chỉ là một ID mới, chưa đăng ký meter nào.
```

Đừng gọi `getId().withName(...)` rồi chờ metric cũ đổi tên trên endpoint hoặc dashboard. Nếu cần thay tên, hãy thiết kế và đăng ký meter mới, đồng thời có cách chuyển đổi dữ liệu và truy vấn thích hợp.

## 4. MeterRegistry: nơi tạo, giữ và tra cứu meter

`MeterRegistry` là lớp trừu tượng tổ chức các meter trong một phạm vi cụ thể. Nó cung cấp các phương thức tiện ích như `counter(...)`, `timer(...)`, `gauge(...)`, API tìm kiếm và cấu hình. Đối tượng meter thực tế được tạo theo kiểu registry và các quy tắc cấu hình của nó.

```text
Tên + tags + loại phép đo
        |
        v
MeterRegistry: áp dụng cấu hình / tìm hoặc tạo meter
        |
        v
Trả về Counter / Timer / Gauge để mã ứng dụng sử dụng
```

### 4.1. Đăng ký không phải lúc nào cũng tạo đối tượng mới

Trong cùng một registry, đăng ký lại một meter cùng tên, cùng tags và loại tương thích thường trả về meter đã có. Ví dụ hai thành phần cùng lấy counter `shop.orders{channel=web,result=success}` thì đang ghi vào cùng một công cụ đo của registry đó.

Điều này giúp tránh vô tình tạo nhiều bộ đếm độc lập cho cùng một phép đo. Tuy nhiên, đăng ký lại để “cập nhật” mô tả, đơn vị hoặc cấu hình không phải cách cấu hình an toàn: meter đã tồn tại thường tiếp tục dùng cấu hình/siêu dữ liệu được áp dụng khi nó được tạo. Hãy hoàn tất cấu hình trước lúc đăng ký.

Registry còn có thể áp dụng `MeterFilter` để đổi tên, bổ sung/lược bỏ tags hoặc từ chối một meter. Hai ID đầu vào tưởng như khác nhau có thể trùng nhau sau khi ánh xạ; meter bị từ chối có thể trả về một đối tượng không ghi nhận dữ liệu. Không được coi việc cầm được một biến `Counter` là bằng chứng metric chắc chắn đang được xuất. [Đăng ký, kiểm tra loại và ánh xạ ID trong MeterRegistry 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java).

### 4.2. Registry là một ranh giới trạng thái

Có hai registry khác nhau thì có thể có hai counter mang ID bằng nhau nhưng giữ trạng thái độc lập. Tăng counter trong registry A không tự làm counter cùng ID trong registry B tăng. Hai ID bằng nhau không chứng minh hai đối tượng Java giống nhau hay hai kho số liệu đã được đồng bộ.

Đây là lỗi thường gặp khi ứng dụng tự gọi `new SimpleMeterRegistry()` trong một service, trong khi Actuator đang đọc registry do Spring quản lý. Service có tăng số đếm, nhưng nó tăng ở một registry khác nên endpoint không thấy dữ liệu đó.

### 4.3. Tìm kiếm và liệt kê

```java
Counter optional = registry.find("shop.orders")
    .tags("channel", "web", "result", "success")
    .counter();

if (optional != null) {
    System.out.println(optional.count());
}

Counter required = registry.get("shop.orders")
    .tags("channel", "web", "result", "success")
    .counter();

int meterCount = registry.getMeters().size();
```

Đây là các đoạn minh họa trong thành phần đã có `registry`. `find(...).counter()` cho phép kết quả không có và trả về `null`. `get(...).counter()` đòi tìm được một counter phù hợp và sẽ ném ngoại lệ nếu không có. Các API tìm kiếm này không đăng ký một meter mới như `registry.counter(...)`.

Khi tra cứu chỉ bằng tên, có thể có nhiều tổ hợp tags phù hợp; đừng hiểu một kết quả tìm được là tổng của tất cả meter cùng tên. Để kiểm chứng một series cụ thể, dùng đầy đủ các chiều phân loại cần thiết.

### 4.4. SimpleMeterRegistry không tự xuất dữ liệu ra ngoài

`SimpleMeterRegistry` giữ các giá trị trong bộ nhớ và phù hợp để thử nghiệm hoặc kiểm thử. Nó không tự gửi số liệu tới Prometheus, Datadog hay một nơi lưu lịch sử. Các registry chuyên biệt bổ sung cơ chế xuất tương ứng; có hệ thống nhận dữ liệu được đẩy theo chu kỳ, có hệ thống kéo dữ liệu từ ứng dụng.

Registry quản lý công cụ đo và trạng thái phục vụ đo lường; hệ thống giám sát thường chịu trách nhiệm lưu lịch sử, truy vấn theo thời gian, biểu đồ và cảnh báo. Không dùng số đếm trong bộ nhớ của một tiến trình thay cho số liệu nghiệp vụ cần độ bền.

## 5. CompositeMeterRegistry: phân phối một lần ghi tới nhiều registry

`CompositeMeterRegistry` cũng là một `MeterRegistry`. Mã nghiệp vụ có thể nhận nó qua kiểu `MeterRegistry`, đăng ký counter/timer bình thường, rồi registry tổng hợp gắn các meter tương ứng vào những registry con.

```text
Mã nghiệp vụ
  Counter nhận từ CompositeMeterRegistry
           |
           | increment()
           +--> Counter trong registry A --> hệ thống giám sát A
           |
           +--> Counter trong registry B --> hệ thống giám sát B
```

Ứng dụng ghi một lần vào composite; mỗi registry con được gắn sẽ nhận lần ghi đó. Đây là cách hỗ trợ nhiều đích giám sát mà không bắt mọi service biết từng hệ thống cụ thể.

### 5.1. Nó không phải phép cộng các registry con

Trong Micrometer 1.13.0, `CompositeCounter.increment(amount)` gọi các counter con, nhưng `count()` **đọc từ một counter con**; nếu chưa có con thì đọc từ đối tượng không ghi nhận với giá trị 0. Nó không cộng các con. [Mã nguồn CompositeCounter 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/composite/CompositeCounter.java).

Nếu A và B cùng ghi nhận 5 đơn thì đó là hai đích nhận dữ liệu của cùng 5 đơn, không phải 10 đơn. Vì vậy cộng số đếm của các con để lấy “tổng composite” sẽ đếm lặp. Cũng không dựa vào thứ tự thêm registry để đoán `count()` chọn con nào; lựa chọn con dùng để đọc không phải một chính sách tổng hợp nghiệp vụ.

Trong ví dụ sau, hai con cố ý được gắn ở thời điểm khác nhau nên có số đếm khác nhau. Khi kiểm tra việc chuyển dữ liệu, hãy đọc từng registry con; giá trị đọc qua composite không phải báo cáo tình trạng của mọi con.

### 5.2. Chưa có registry con thì dữ liệu ghi không được giữ để phát lại

Có thể tạo một counter trong composite trước khi thêm registry con. Counter đó là công cụ đo hợp lệ về mặt API, nhưng các lần tăng khi chưa có con không trở thành một hàng đợi chờ xử lý. Khi thêm con sau đó, Micrometer đăng ký meter tương ứng cho con mới; nó không phát lại lịch sử tăng trước khi gắn con.

Ngay cả khi A đã ghi được dữ liệu, thêm B sau đó cũng không sao chép số đếm đang có ở A sang B. Đây là lý do nên hoàn tất việc gắn registry trước khi bắt đầu ghi dữ liệu thực tế. [Hành vi registry tổng hợp trong tài liệu Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

### 5.3. Việc ghi trực tiếp vào registry con không đi ngược lên composite

Nếu mã lấy riêng counter của A rồi tăng trực tiếp, B không tự nhận lần tăng đó. Composite chỉ phân phối những thao tác được gọi qua meter thuộc composite; nó không theo dõi mọi thay đổi trong từng con để đồng bộ hai chiều.

Gỡ A bằng `composite.remove(a)` dừng chuyển các lần ghi tiếp theo tới A; không có nghĩa dữ liệu đã được gửi ra hệ thống giám sát A bị xóa. Registry con còn là đối tượng có vòng đời riêng. Trong ứng dụng Spring, để thành phần quản lý vòng đời đóng registry; service nghiệp vụ không tự đóng registry dùng chung.

Composite cũng không phải cơ chế lưu bền, bộ đệm khi mất mạng, hay bộ tổng hợp số liệu giữa nhiều instance ứng dụng. Việc truyền dữ liệu ra mạng và khả năng xử lý lỗi phụ thuộc registry/exporter cụ thể.

## 6. Chương trình Java độc lập để kiểm chứng

Ví dụ dùng hai `SimpleMeterRegistry` làm hai đích trong bộ nhớ. Chúng giúp quan sát chính xác cơ chế, không cần khởi động Spring, HTTP server hoặc một hệ thống giám sát bên ngoài.

Tạo dự án Gradle Java có wrapper và JDK 17 khả dụng. Cấu trúc:

```text
meter-roles-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat và gradle/wrapper/
  src/main/java/MeterRolesDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'meter-roles-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'MeterRolesDemo'
}
```

`src/main/java/MeterRolesDemo.java`:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MeterRolesDemo {

    public static void main(String[] args) {
        identityAndRegistry();
        compositeRouting();
    }

    private static void identityAndRegistry() {
        SimpleMeterRegistry local = new SimpleMeterRegistry();
        SimpleMeterRegistry isolated = new SimpleMeterRegistry();
        try {

            Counter first = Counter.builder("shop.orders")
                .tags("channel", "web", "result", "success")
                .description("Completed orders")
                .baseUnit("orders")
                .register(local);

            Counter again = Counter.builder("shop.orders")
                .tags("result", "success", "channel", "web")
                .description("Another description")
                .register(local);

            Counter failed = local.counter(
                "shop.orders", "channel", "web", "result", "failure");

            first.increment(2);
            again.increment();
            failed.increment();

            Meter meter = first;
            Meter.Id id = meter.getId();
            Meter.Id metadataOnly = new Meter.Id(
                id.getName(), Tags.of(id.getTags()),
                "requests", "Different metadata", Meter.Type.TIMER);
            Meter.Id renamed = id.withName("shop.orders.renamed");

            System.out.println("sameInstance=" + (first == again));
            System.out.println("type=" + id.getType());
            System.out.println("channel=" + id.getTag("channel"));
            System.out.println("successCount=" + first.count());
            System.out.println("failureCount=" + failed.count());
            System.out.println("localMeters=" + local.getMeters().size());
            System.out.println("differentTagsSameId="
                + id.equals(failed.getId()));
            System.out.println("metadataOnlySameId=" + id.equals(metadataOnly));
            System.out.println("originalName=" + id.getName());
            System.out.println("derivedName=" + renamed.getName());
            System.out.println("originalDescription=" + id.getDescription());

            for (var measurement : meter.measure()) {
                System.out.println("measurement="
                    + measurement.getStatistic() + ":" + measurement.getValue());
            }

            Counter other = Counter.builder("shop.orders")
                .tags("channel", "web", "result", "success")
                .register(isolated);
            other.increment(7);
            System.out.println("acrossRegistriesSameId="
                + id.equals(other.getId()));
            System.out.println("acrossRegistriesSameObject=" + (first == other));
            System.out.println("isolatedCount=" + other.count());
            System.out.println("localStill=" + first.count());

            boolean typeConflict = false;
            try {
                Timer.builder("shop.orders")
                    .tags("channel", "web", "result", "success")
                    .register(local);
            }
            catch (IllegalArgumentException exception) {
                typeConflict = true;
            }
            System.out.println("typeConflict=" + typeConflict);
        }
        finally {
            isolated.close();
            local.close();
        }
    }

    private static void compositeRouting() {
        CompositeMeterRegistry composite = new CompositeMeterRegistry();
        SimpleMeterRegistry a = new SimpleMeterRegistry();
        SimpleMeterRegistry b = new SimpleMeterRegistry();
        try {

            Counter jobs = composite.counter("batch.jobs", "queue", "daily");
            jobs.increment(5);
            System.out.println("emptyCompositeCount=" + jobs.count());

            composite.add(a);
            jobs.increment(2);
            System.out.println("aAfterAttach=" + a.get("batch.jobs").counter().count());

            composite.add(b);
            System.out.println("bAtAttach=" + b.get("batch.jobs").counter().count());

            jobs.increment(3);
            double countA = a.get("batch.jobs").counter().count();
            double countB = b.get("batch.jobs").counter().count();
            double view = jobs.count();
            System.out.println("aAfterFanout=" + countA);
            System.out.println("bAfterFanout=" + countB);
            System.out.println("compositeReadsOneChild="
                + (view == countA || view == countB));
            System.out.println("compositeReadsSum=" + (view == countA + countB));
            System.out.println("logicalMeters=" + composite.getMeters().size());
            System.out.println("childRegistries=" + composite.getRegistries().size());

            composite.remove(a);
            jobs.increment();
            System.out.println("aAfterDetach=" + a.get("batch.jobs").counter().count());
            System.out.println("bAfterDetach=" + b.get("batch.jobs").counter().count());
        }
        finally {
            composite.close();
            a.close();
            b.close();
        }
    }
}
```

Chạy tại thư mục dự án; Gradle biên dịch Java rồi thực thi `main`:

```bash
./gradlew -q run --console=plain
```

Trên Windows PowerShell dùng `.\gradlew.bat -q run --console=plain`. Đầu ra của chương trình:

```text
sameInstance=true
type=COUNTER
channel=web
successCount=3.0
failureCount=1.0
localMeters=2
differentTagsSameId=false
metadataOnlySameId=true
originalName=shop.orders
derivedName=shop.orders.renamed
originalDescription=Completed orders
measurement=COUNT:3.0
acrossRegistriesSameId=true
acrossRegistriesSameObject=false
isolatedCount=7.0
localStill=3.0
typeConflict=true
emptyCompositeCount=0.0
aAfterAttach=2.0
bAtAttach=0.0
aAfterFanout=5.0
bAfterFanout=3.0
compositeReadsOneChild=true
compositeReadsSum=false
logicalMeters=1
childRegistries=2
aAfterDetach=5.0
bAfterDetach=4.0
```

Ví dụ cần thư viện Micrometer và các phụ thuộc được Gradle giải quyết; không biên dịch bằng một lệnh `javac` thiếu classpath. Nếu tự dùng `javac`/`java`, phải đưa các JAR runtime đã giải quyết vào classpath khi biên dịch và khi chạy; dấu phân cách classpath trên Windows là `;`, trên Linux/macOS là `:`.

### 6.1. Giải thích phần danh tính và registry

`sameInstance=true` xác nhận việc đăng ký lại counter cùng tên/tags trong `local` trả về đối tượng đã có. Thứ tự hai cặp tags bị đảo không tạo danh tính khác. Do `first` và `again` cùng trỏ tới một counter, tăng 2 qua biến thứ nhất rồi tăng 1 qua biến thứ hai cho kết quả 3.

`failureCount=1.0` thuộc counter khác vì `result=failure`. Vì vậy `localMeters=2`, mặc dù cả hai cùng có tên `shop.orders`. `metadataOnlySameId=true` chỉ kiểm chứng quy tắc so sánh ID: đối tượng `metadataOnly` không được dùng để đăng ký timer. Thử đăng ký timer sau đó dẫn tới `typeConflict=true`, thể hiện registry vẫn bảo vệ tính tương thích của loại.

`originalDescription=Completed orders` cho thấy lần đăng ký lại bằng mô tả khác không thay mô tả đã có trong tình huống này. `derivedName` là ID mới được tạo ra, trong khi `originalName` giữ nguyên. Không có meter tên mới nào được đăng ký chỉ bằng lời gọi `withName()`.

`acrossRegistriesSameId=true` đi cùng `acrossRegistriesSameObject=false` và hai giá trị 3, 7. Danh tính giống nhau trong hai registry không đồng nghĩa dùng chung bộ đếm.

### 6.2. Giải thích phần composite theo từng thời điểm

| Thời điểm | Thao tác | A | B | Điều rút ra |
| --- | --- | --- | --- | --- |
| Chưa gắn con | `jobs.increment(5)` | Chưa có meter | Chưa có meter | Composite không lưu 5 để phát lại |
| Gắn A, rồi tăng 2 | `add(a)` và `increment(2)` | 2 | Chưa có meter | A chỉ nhận thao tác từ lúc nó được gắn |
| Gắn B | `add(b)` | 2 | 0 | B không được sao chép số 2 từ A |
| Tăng thêm 3 qua composite | `increment(3)` | 5 | 3 | Cả hai con nhận cùng lần ghi mới |
| Gỡ A, tăng thêm 1 | `remove(a)` và `increment()` | 5 | 4 | A không còn nhận lần ghi mới |

`logicalMeters=1` là một meter logic trong composite, còn `childRegistries=2` là số registry con tại thời điểm in. Không lấy phép nhân/hợp các con này làm số sự kiện nghiệp vụ.

Chương trình chỉ in `compositeReadsOneChild=true` và `compositeReadsSum=false`, tránh buộc đầu ra vào một lựa chọn con không được bảo đảm. Việc mỗi đích giữ dữ liệu ra sao được xác nhận trực tiếp bằng `a.get(...).counter().count()` và `b.get(...).counter().count()`.

## 7. Áp dụng trong Spring Boot Actuator

Trong ứng dụng Boot, tiêm `MeterRegistry` do Spring quản lý vào thành phần cần đo. Không tự tạo registry mới trong từng service và cũng không ép kiểu registry thành `SimpleMeterRegistry` hay `CompositeMeterRegistry` để ghi một counter thông thường.

Ví dụ một thành phần nghiệp vụ, nằm trong dự án Boot đã có Actuator và Micrometer:

```java
package example.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {
    private final Counter success;
    private final Counter failure;

    public CheckoutMetrics(MeterRegistry registry) {
        this.success = Counter.builder("app.checkout.completed")
            .tag("result", "success")
            .description("Completed checkout attempts")
            .register(registry);
        this.failure = Counter.builder("app.checkout.completed")
            .tag("result", "failure")
            .description("Completed checkout attempts")
            .register(registry);
    }

    public void recordCompletion(boolean successful) {
        (successful ? success : failure).increment();
    }
}
```

Đây là component tích hợp, không phải chương trình độc lập có `main`. Mã gọi `recordCompletion(...)` đúng một lần ở điểm kết thúc đã định nghĩa cho mỗi lượt thanh toán. Hai counter được đăng ký một lần trong hàm tạo và giữ trong trường; không phải tạo registry hoặc cấu hình exporter mỗi lần có giao dịch.

Để thêm tags dùng chung trước khi các meter được đăng ký, có thể cung cấp cấu hình:

```java
package example.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonMetricsTags() {
        return registry -> registry.config()
            .commonTags("application", "checkout");
    }
}
```

Đừng thêm tags chung sau khi service đã đăng ký meter rồi chờ tất cả ID cũ tự được viết lại. Cấu hình registry, filters và các chiều dùng chung nên hoàn tất trước lúc ghi nhận.

### 7.1. Không phụ thuộc cứng vào lớp registry được tiêm

Tài liệu tổng quan Boot mô tả tự cấu hình registry tổng hợp cho các hệ thống giám sát có trên classpath. Khi đọc triển khai **Boot 3.3.0**, cần hiểu điều kiện cụ thể hơn: cấu hình composite được áp dụng khi đã có registry nhưng không có một ứng viên duy nhất để tiêm; một registry đơn hoặc một ứng viên `@Primary` có thể được dùng trực tiếp. Vì vậy không thể khẳng định mọi bean `MeterRegistry` được tiêm đều là một `CompositeMeterRegistry`.

Đây là chỗ mô tả tổng quan được giản lược so với điều kiện trong mã. Lựa chọn ổn định cho service là phụ thuộc vào `MeterRegistry`; khi cần chẩn đoán, kiểm tra các bean thực tế và điều kiện tự cấu hình. [Tổng quan Metrics của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html), [điều kiện CompositeMeterRegistryConfiguration 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/CompositeMeterRegistryConfiguration.java).

### 7.2. Phân biệt registry ứng dụng, global registry và endpoint

`Metrics.globalRegistry` là một composite tĩnh do Micrometer cung cấp; các phương thức tĩnh như `Metrics.counter(...)` sử dụng nó. Nó không đồng nhất về mặt đối tượng với mọi registry được tiêm từ Spring. Boot có cơ chế thêm các registry tự cấu hình vào global registry theo cấu hình `management.metrics.use-global-registry`; có thể tắt kết nối đó khi ứng dụng cần cách ly trạng thái tĩnh.

Trong mã ứng dụng Spring, tiêm registry thường làm quyền sở hữu và kiểm thử rõ ràng hơn. Trong kiểm thử, một registry tĩnh dùng chung còn có thể giữ meter từ phép thử trước nếu không quản lý vòng đời. Không tự thêm một registry vào global hoặc composite chỉ vì giá trị chưa hiện lên: trước hết xác nhận đang ghi vào đâu.

Endpoint `/actuator/metrics` là một cách chẩn đoán số liệu qua HTTP khi nó được bật, được expose và người đọc có quyền thích hợp. Nó không phải `MeterRegistry`, và expose endpoint này không tự biến `SimpleMeterRegistry` thành một exporter. Việc xuất sang hệ thống đích phụ thuộc registry tương ứng và cấu hình của hệ thống đó.

Tên khai báo theo dạng như `app.checkout.completed` là tên Micrometer. Registry/exporter có thể chuyển tên sang quy ước của hệ thống giám sát, thêm hậu tố hoặc chuyển đơn vị. Khi tra cứu trong registry, phân biệt tên chuẩn trong ứng dụng với tên đã được xuất trên hệ thống đích.

## 8. Thiết kế tên và tags để registry có thể quản lý được

Tên nên mô tả hiện tượng đo; tags nên mô tả các chiều phân loại hữu hạn và có ích cho truy vấn. Chẳng hạn `result=success|failure` và `channel=web|mobile` cho số tổ hợp danh tính nhỏ, có thể hiểu được.

Tránh đưa mã đơn hàng, ID người dùng, UUID, chuỗi thời gian hoặc URL thô có ID vào tag. Mỗi tổ hợp giá trị mới làm tăng số meter và số chuỗi thời gian có thể được xuất. Với 2 kênh × 3 kết quả × 4 vùng, có tối đa 24 tổ hợp cho tên meter đó nếu tất cả xuất hiện; thêm một triệu mã đơn có thể làm không gian danh tính tăng rất lớn.

Số 24 là số tổ hợp tên/tags trong ví dụ, chưa bao gồm việc một loại meter có thể tạo nhiều chuỗi thời gian, tags hạ tầng hoặc các instance khác nhau. Vì vậy đếm `getMeters().size()` không đủ để dự báo toàn bộ chi phí ở hệ thống giám sát.

Với composite, một thiết kế tags không giới hạn được chuyển tới nhiều registry con và có thể nhân chi phí ở nhiều nơi. Composite không tự làm sạch tags, giảm số tổ hợp hay chuyển dữ liệu nhạy cảm thành an toàn.

Các tags chung, filters và quy ước tên có thể khác giữa registry con, nên ID ở từng con sau ánh xạ có thể không giống từng ký tự với ID logic ở composite. Khi chẩn đoán, xem ID thực tế ở đúng registry và dữ liệu thật được xuất; không chỉ nhìn tên biến Java.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu cần dùng |
| --- | --- |
| `Meter` là một số duy nhất | Nó là công cụ cung cấp một tập phép đo; số thống kê tùy loại |
| `Meter.Id` giữ số đếm hiện tại | ID giữ tên/tags/siêu dữ liệu, không giữ giá trị counter |
| Đổi description sẽ tạo meter mới | Danh tính dựa trên tên và tags; thay metadata không tách danh tính |
| ID bằng nhau thì cùng đối tượng ở mọi nơi | Việc dùng lại meter có phạm vi registry; hai registry có thể giữ trạng thái độc lập |
| Counter và Timer có thể chung ID vì `equals` bỏ qua type | Registry còn kiểm tra loại và có thể từ chối đăng ký |
| `withName()` đổi tên meter đã đăng ký | Nó tạo một ID mới, không đổi meter cũ |
| `SimpleMeterRegistry` tự đẩy dữ liệu ra mạng | Nó giữ giá trị trong bộ nhớ, không tự xuất tới hệ thống khác |
| Composite giữ số liệu để gửi bù khi thêm con | Các lần ghi trước khi con được gắn không được phát lại |
| `CompositeCounter.count()` là tổng các con | Trong phiên bản minh họa, nó đọc một con; không cộng các con |
| Tăng cả composite và từng con để chắc dữ liệu tới nơi | Có thể ghi lặp; mã nghiệp vụ nên dùng đúng một đường ghi đã chọn |
| Tạo registry mới giúp Actuator tự nhìn thấy metric | Registry ngoài phạm vi quản lý không tự trở thành nguồn dữ liệu của Actuator |
| Một meter tương ứng đúng một chuỗi thời gian | Loại meter và exporter quyết định có bao nhiêu thống kê/chuỗi được xuất |

Khi số liệu không như mong đợi, lần lượt kiểm tra: **đúng registry chưa → tên và tags cuối cùng là gì → đã có meter phù hợp chưa → composite có con chưa → đang đọc con nào → exporter đã được cấu hình chưa**. Đây là các ranh giới khác nhau và cần bằng chứng riêng.

## 10. Tự kiểm tra

1. Đăng ký hai counter cùng tên/tags nhưng đảo thứ tự tags trong cùng một `SimpleMeterRegistry`. Dự đoán quan hệ `==` và kết quả nếu tăng qua cả hai biến.
2. Giữ tên, đổi `result=success` thành `result=failure`. Giải thích vì sao có meter khác, rồi phân biệt số meter với số chuỗi thời gian ở hệ thống đích.
3. Tạo hai registry độc lập có counter cùng ID. Tăng chỉ ở registry thứ nhất; giải thích vì sao ID bằng nhau nhưng giá trị khác nhau.
4. Tăng counter trong composite trước khi thêm con. Dự đoán giá trị con mới và giải thích vì sao không có dữ liệu gửi bù.
5. Gắn con A, ghi 2; gắn con B, ghi 3. Nêu giá trị từng con và lý do không diễn giải `count()` của composite như phép tổng.
6. Trong ứng dụng Boot, một service đếm được số liệu nhưng Actuator không thấy. Kiểm tra nguồn registry của service trước khi sửa quyền HTTP hoặc cài thêm một hệ thống giám sát.
7. Giải thích vì sao một service chỉ cần nhận `MeterRegistry`, trong khi cấu hình hạ tầng mới cần quan tâm registry nào xuất tới hệ thống nào.

Khi đọc được một dòng `counter.increment()`, người học cần xác định được cả bốn yếu tố: công cụ đang ghi là gì, ID nào nhận dữ liệu, registry nào sở hữu nó, và có composite nào phân phối lần ghi tới các registry con hay không.
