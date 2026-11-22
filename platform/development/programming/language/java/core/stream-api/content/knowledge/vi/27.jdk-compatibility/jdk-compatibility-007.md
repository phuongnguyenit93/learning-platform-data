# Xác định JDK tối thiểu và chọn cách triển khai tương thích

Khi phát triển ứng dụng bằng **Java Stream API**, một đoạn mã chạy tốt trên máy lập trình chưa chắc chạy được ở môi trường triển khai. Chẳng hạn, `stream().toList()` rất thuận tiện trên Java 17 nhưng **không tồn tại trong Java 8**; `Collectors.teeing()` cần Java 12 trở lên; còn **Stream Gatherers** chỉ trở thành API chính thức từ Java 24. Nếu sản phẩm phải chạy trên JDK cũ hơn, lựa chọn API cần được quyết định **trước khi viết hoặc nâng cấp pipeline**.

Bài học **“Xác định JDK tối thiểu và chọn cách triển khai tương thích”** thuộc chương **Khả năng tương thích JDK** của module **JAVA_STREAM_API**. Nội dung gắn với quá trình học pipeline khai báo và lazy bằng `filter`, `map`, `reduce`, `collect`, grouping, collector tùy chỉnh, `Spliterator`, Stream song song và Stream Gatherers; đồng thời chỉ ra các giới hạn về phiên bản, trạng thái, tài nguyên và hiệu năng.

Mục tiêu là giúp bạn:

1. Phân biệt phiên bản JDK **dùng để biên dịch**, phiên bản **mã nguồn/API yêu cầu** và phiên bản **runtime thực tế**.
2. Lập bảng kiểm các API/syntax trước khi chốt **JDK tối thiểu**.
3. Sử dụng `javac --release` để tránh vô tình gọi API mới trong bản build dành cho JDK cũ.
4. Lựa chọn phương án thay thế có **ngữ nghĩa tương đương**, không chỉ tương tự về cú pháp.
5. Viết và kiểm tra một dự án tổng hợp bằng Java 8, sau đó biết khi nào nên dùng API của Java 9, 12, 16 hay 24.
6. Xây ma trận kiểm thử khi nâng JDK, cập nhật thư viện hoặc dùng API preview.

> **Phạm vi:** các mốc phiên bản dưới đây là thời điểm API/cú pháp lần đầu có trong Java SE/JDK. “JDK tối thiểu” khi triển khai còn phụ thuộc thư viện bên thứ ba, hệ điều hành, chính sách hỗ trợ và môi trường thực thi của tổ chức. Không nên lấy “phiên bản đang cài trên máy” làm yêu cầu sản phẩm một cách tự động.

## 1. Một chương trình Java có những “phiên bản” nào?

Trước tiên, phân biệt bốn khái niệm thường bị gộp làm một.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **JDK dùng để build** | Trình biên dịch `javac` đang chạy ở đâu? | Build bằng JDK 17 |
| **Mức ngôn ngữ (source level)** | Code được phép dùng cú pháp nào? | Dùng lambda Java 8, không dùng `record` |
| **Mức API/bytecode mục tiêu** | Code được phép gọi thư viện chuẩn nào và sinh class cho JVM nào? | `--release 8` |
| **Runtime triển khai** | Máy chạy ứng dụng thực sự có phiên bản Java nào? | Production dùng Java 8 hoặc 17 |

Ví dụ: một nhóm phát triển có thể **dùng JDK 17 để biên dịch code Java 8**, miễn cấu hình build bảo đảm cả cú pháp, API chuẩn và bytecode đều tương thích Java 8. Nhưng nếu dùng `record` hoặc `Stream.toList()` trong phần code phải chạy trên Java 8, việc “máy build có JDK 17” không làm các tính năng ấy xuất hiện ở runtime cũ.

### 1.1. Hai loại lỗi rất khác nhau

**Dùng class file quá mới:** JVM cũ không hiểu định dạng bytecode do compiler mới sinh, thường gây `UnsupportedClassVersionError`.

**Class file đủ cũ nhưng gọi API mới:** nếu build cấu hình thiếu kiểm tra API chuẩn, code có thể được phát hành dưới bytecode Java 8 nhưng gọi `String.isBlank()` hoặc `Stream.toList()`. Trên Java 8, lời gọi đó không tồn tại, có thể dẫn đến `NoSuchMethodError` khi thực thi đường code liên quan.

Bởi vậy, **không thể chỉ nhìn phiên bản class file** để kết luận một ứng dụng chạy được trên JDK tối thiểu.

~~~mermaid
flowchart TD
    A["Mã nguồn Java"] --> B["Kiểm tra cú pháp"]
    B --> C["Kiểm tra API chuẩn"]
    C --> D["Biên dịch bytecode"]
    D --> E["Kiểm tra dependencies"]
    E --> F["Chạy trên runtime tối thiểu"]
    F --> G["Kiểm thử kết quả và tài nguyên"]
~~~

Một mắt xích không đạt có thể khiến lời hứa “hỗ trợ JDK X” không còn đúng.

## 2. Cách xác định JDK tối thiểu từ yêu cầu sản phẩm

Đừng bắt đầu bằng câu hỏi “nên dùng JDK mới nhất hay không?”. Hãy bắt đầu từ **hợp đồng triển khai**.

Một quy trình thực tế:

1. **Liệt kê runtime cần hỗ trợ:** máy chủ, desktop, thiết bị, CI, môi trường khách hàng, container, job batch.
2. **Xác định phiên bản thấp nhất bắt buộc:** do yêu cầu sản phẩm hoặc hợp đồng vận hành.
3. **Liệt kê tính năng sử dụng:** syntax (ví dụ `record`), API (`teeing`), bộ thư viện, annotation processor, agent và tool build.
4. **Tính mốc tối thiểu của từng phụ thuộc** và tìm xung đột với runtime mục tiêu.
5. **Chọn cách triển khai:** dùng API cũ tương đương, tăng baseline, tách module mới hoặc duy trì hai cách triển khai.
6. **Build và chạy test trên runtime thấp nhất**; sau đó kiểm tra thêm các runtime cao hơn cần hỗ trợ.

Ví dụ, nếu ứng dụng bắt buộc chạy trên Java 11 nhưng thiết kế đang sử dụng `Collectors.teeing()`, ta có ba lựa chọn chính: viết collector thay thế trên Java 11, đổi yêu cầu runtime tối thiểu thành Java 12+ nếu được phép, hoặc cô lập tính năng vào thành phần riêng chỉ chạy trên runtime phù hợp.

**Không được tự chọn tăng baseline** khi yêu cầu vận hành đã khóa Java 11; cũng không nên cố viết lại một API phức tạp nếu dự án thực tế đã được phép chuyển lên Java mới và việc nâng cấp đem lại lợi ích bảo trì rõ ràng.

## 3. Bảng mốc Java Stream API và các tiện ích thường dùng

Bảng sau tập trung vào những phiên bản có ảnh hưởng rõ đến thiết kế pipeline và bài thực hành trong module.

| Mốc Java | API hoặc cú pháp tiêu biểu | Ý nghĩa khi chọn baseline |
|---|---|---|
| **8** | `Stream`, `IntStream`, `LongStream`, `DoubleStream`, `filter`, `map`, `flatMap`, `reduce`, `collect`, `Collectors.groupingBy`, `partitioningBy`, `joining`, `Spliterator`, `StreamSupport`, `Files.lines` | Nền tảng của phần lớn bài học Stream |
| **9** | `Stream.ofNullable`, `takeWhile`, `dropWhile`, `iterate(seed, hasNext, next)`, `Optional.stream`, `Collectors.filtering`, `Collectors.flatMapping`, `List.of` | Cú pháp ngắn hơn và một số khả năng xử lý mới |
| **10** | `Collectors.toUnmodifiableList`, `List.copyOf`, suy luận biến cục bộ `var` | Chọn rõ tính không thể sửa; `var` không dùng được ở source level 8 |
| **11** | `String.isBlank`, `Path.of` | Tiện ích thường vô tình lọt vào code gọi Stream dù không thuộc API Stream |
| **12** | `Collectors.teeing` | Thu hai kết quả rồi gộp trong một collector |
| **14** | Switch expression chính thức | Cú pháp tiện cho các phép ánh xạ theo trạng thái |
| **16** | `Stream.toList`, `Stream.mapMulti`, `record` chính thức | Giảm boilerplate nhưng tăng mức JDK/source tối thiểu |
| **17** | Phiên bản LTS được nhiều dự án sử dụng; các API trên vẫn có mặt | Baseline thực tế thường cần xét cùng chính sách vận hành |
| **21** | Phiên bản LTS; tiếp tục có các API Stream đã chuẩn hóa trước đó | Có thể là baseline mới tùy môi trường |
| **24** | `Stream.gather`, `Gatherer` và các built-in `Gatherers` thành API chính thức | Cần Java 24+ nếu dùng trực tiếp Gatherers chuẩn |

Một số lưu ý:

- `Collectors.teeing` **không có trong Java 8 hoặc 11**.
- `Stream.toList()` **không có trong Java 11**, dù `Collectors.toList()` đã có từ Java 8.
- `Stream.mapMulti` và `Stream.toList` đều đến ở Java 16, nhưng **không có cùng ngữ nghĩa**.
- `record` là **tính năng ngôn ngữ**, không phải phương thức Stream. Một ví dụ dùng `record` không thể biên dịch ở source level 8 dù phần pipeline Stream chỉ gọi các API Java 8.
- Stream Gatherers từng xuất hiện dưới dạng **preview** ở Java 22 và 23; API chính thức là Java 24. Một bản preview không đồng nghĩa với cam kết tương thích mã nguồn/nhị phân như API chuẩn.

**Lưu ý về bảo trì:** mốc API tối thiểu là thông tin lâu dài; tình trạng còn được nhà cung cấp hỗ trợ, bản vá bảo mật và LTS của một runtime là **quyết định vận hành theo thời điểm**, cần kiểm tra chính sách hiện hành của nhà cung cấp thay vì suy ra trực tiếp từ bảng trên.

## 4. Đọc và xác nhận phiên bản trong môi trường thực tế

Trước khi kết luận một lỗi tương thích, xác nhận cả compiler và runtime đang dùng.

~~~powershell
java -version
javac -version
~~~

Lệnh `java -version` dùng được trên Java 8; từ Java 9 trở lên cũng có cú pháp `java --version`. Kết quả của hai lệnh cần được kiểm tra riêng vì trong môi trường có nhiều bản cài, `java` và `javac` **có thể trỏ tới hai JDK khác nhau**.

Ví dụ tình huống:

~~~text
java  -> runtime Java 8
javac -> compiler JDK 17
~~~

Đây không tự động là cấu hình sai. Nhưng build phải dùng mục tiêu tương thích Java 8 và kiểm thử trên runtime Java 8 trước khi phát hành.

Các thông tin cần ghi trong báo cáo build:

- Phiên bản compiler và bản phân phối JDK.
- Cấu hình `--release` hoặc toolchain mục tiêu.
- Runtime thấp nhất cam kết.
- Phiên bản các dependency trực tiếp và runtime library quan trọng.
- Hệ điều hành/kiến trúc triển khai nếu có thư viện native hoặc phụ thuộc môi trường.

Không suy luận runtime của production chỉ từ phiên bản JDK dùng trong IDE cá nhân.

## 5. Dùng javac --release để xây bản tương thích

Từ **JDK 9**, `javac` có tùy chọn `--release` để biên dịch hướng đến một phiên bản Java được compiler hỗ trợ.

Ví dụ dùng JDK hiện đại biên dịch code Java 8:

~~~powershell
javac --release 8 -d out8 MinJdkEightExample.java
~~~

Tùy chọn này đồng thời ràng buộc:

1. **Cú pháp** theo mức ngôn ngữ mục tiêu.
2. **API chuẩn được phép sử dụng** trong phiên bản Java mục tiêu.
3. **Định dạng class file** tương ứng.

Vì vậy, nếu mã sử dụng `Stream.toList()`, `Collectors.teeing()` hoặc `String.isBlank()` mà biên dịch với `--release 8`, compiler sẽ không chấp nhận lời gọi API đó.

### 5.1. Vì sao -source và -target thôi chưa đủ?

Ví dụ cấu hình cũ:

~~~powershell
javac -source 8 -target 8 -d out8 Example.java
~~~

`-source 8` kiểm tra mức cú pháp và `-target 8` đặt phiên bản class file, **nhưng có thể vẫn biên dịch lời gọi tới API mới của JDK đang chạy compiler** nếu không sử dụng đúng bootclasspath/API mục tiêu. Ví dụ code chứa `"hello".isBlank()` có thể biên dịch thành bytecode mức 8 khi build bằng JDK mới trong cấu hình không kiểm soát API, nhưng khi chạy ở Java 8 lại không tìm được phương thức.

Do đó, khi compiler hỗ trợ, ưu tiên **`--release 8`** thay vì chỉ kết hợp `-source 8 -target 8`.

### 5.2. Hai giới hạn của --release

- Không phải mọi JDK mới đều hỗ trợ biên dịch về **mọi** phiên bản cũ; cần kiểm tra danh sách `--release` của compiler đang dùng.
- `--release` chủ yếu kiểm soát cú pháp, class file và **API nền tảng Java**. Nó **không tự bảo đảm mọi thư viện bên thứ ba**, plugin, agent hay thư viện native đều chạy được trên runtime đích.

**Không dùng đồng thời `--release` với các tùy chọn source/target hoặc cấu hình hệ thống mâu thuẫn.** Với dự án build bằng Maven/Gradle, hãy quản lý mức đích nhất quán tại một nơi.

## 6. Dự án Java 8 hoàn chỉnh: báo cáo thanh toán không cần API mới

Để thấy cách chọn baseline tác động đến code, ta viết một chương trình **Java 8 thật sự**: không dùng `record`, `List.of`, `Stream.toList`, `teeing`, `var` hay `Map.copyOf`.

**Yêu cầu:** từ các giao dịch, thống kê số khoản thanh toán thành công, tổng tiền và tổng tiền theo khu vực. Code phải tuân thủ hợp đồng collector, có thể chạy tuần tự hoặc song song nếu dữ liệu đầu vào ổn định.

Đặt trong file `MinJdkEightExample.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collector;

public final class MinJdkEightExample {

    static final class Payment {
        private final String region;
        private final long amountVnd;
        private final boolean paid;

        Payment(String region, long amountVnd, boolean paid) {
            this.region = Objects.requireNonNull(region, "region");
            if (region.trim().isEmpty()) {
                throw new IllegalArgumentException("region rỗng");
            }
            if (amountVnd < 0L) {
                throw new IllegalArgumentException("amountVnd âm");
            }
            this.amountVnd = amountVnd;
            this.paid = paid;
        }

        String getRegion() { return region; }
        long getAmountVnd() { return amountVnd; }
        boolean isPaid() { return paid; }
    }

    static final class Report {
        private final long count;
        private final long totalVnd;
        private final Map<String, Long> byRegion;

        Report(long count, long totalVnd, Map<String, Long> byRegion) {
            this.count = count;
            this.totalVnd = totalVnd;
            // Sao chép trước khi tạo view không thể sửa.
            this.byRegion = Collections.unmodifiableMap(
                new TreeMap<String, Long>(byRegion)
            );
        }

        long getCount() { return count; }
        long getTotalVnd() { return totalVnd; }
        Map<String, Long> getByRegion() { return byRegion; }
    }

    static final class MutableReport {
        private long count;
        private long totalVnd;
        private final Map<String, Long> byRegion =
            new HashMap<String, Long>();

        void add(Payment payment) {
            if (!payment.isPaid()) {
                return;
            }
            count = Math.addExact(count, 1L);
            totalVnd = Math.addExact(totalVnd, payment.getAmountVnd());

            String region = payment.getRegion();
            Long previous = byRegion.get(region);
            long oldValue = previous == null ? 0L : previous;
            byRegion.put(region,
                Math.addExact(oldValue, payment.getAmountVnd()));
        }

        MutableReport merge(MutableReport other) {
            count = Math.addExact(count, other.count);
            totalVnd = Math.addExact(totalVnd, other.totalVnd);

            other.byRegion.forEach((region, amount) -> {
                Long previous = byRegion.get(region);
                long oldValue = previous == null ? 0L : previous;
                byRegion.put(region, Math.addExact(oldValue, amount));
            });
            return this;
        }

        Report finish() {
            return new Report(count, totalVnd, byRegion);
        }
    }

    static Report summarize(List<Payment> payments) {
        Objects.requireNonNull(payments, "payments");

        return payments.stream().collect(Collector.of(
            MutableReport::new,
            MutableReport::add,
            MutableReport::merge,
            MutableReport::finish
        ));
    }

    public static void main(String[] args) {
        List<Payment> payments = Arrays.asList(
            new Payment("North", 120_000L, true),
            new Payment("South",  70_000L, false),
            new Payment("North",  80_000L, true),
            new Payment("South",  50_000L, true)
        );

        Report report = summarize(payments);

        System.out.println(report.getCount());       // 3
        System.out.println(report.getTotalVnd());    // 250000
        System.out.println(report.getByRegion());
        // {North=200000, South=50000}

        Report empty = summarize(Collections.<Payment>emptyList());
        System.out.println(empty.getCount());        // 0
        System.out.println(empty.getByRegion().isEmpty()); // true
    }
}
~~~

### 6.1. Vì sao ví dụ đáp ứng Java 8?

- `static final class Payment` và `Report` thay cho `record`.
- `Arrays.asList(...)` thay cho `List.of(...)`.
- `Collector.of(supplier, accumulator, combiner, finisher)` đã có từ Java 8.
- `Math.addExact` đã có trong Java 8; nó báo lỗi nếu tổng `long` bị tràn thay vì trả số sai.
- `Collections.unmodifiableMap(new TreeMap<>(...))` tạo bản sao rồi cung cấp view không cho sửa, thay cho `Map.copyOf` của Java 10.
- Các lambda và method reference đều là cú pháp Java 8.

Đây là một ví dụ về **mutable reduction**: `MutableReport` là bộ chứa trung gian được collector tạo và gộp, còn `Report` là kết quả cuối. Code không dùng một `HashMap` chia sẻ bên ngoài pipeline, nên tránh lỗi thường gặp của `parallelStream().forEach(sharedMap::put)`.

### 6.2. Những điều ví dụ chưa bảo đảm

Dù mã có thể biên dịch bằng Java 8, hệ thống nghiệp vụ vẫn cần quyết định xử lý ID trùng, xác thực dữ liệu nguồn, thời điểm ghi dữ liệu, lỗi I/O và giới hạn kích thước. Bài này tập trung vào **mức tương thích và hợp đồng Stream**, không phải một hệ thống tài chính hoàn chỉnh.

Ví dụ trên không thay đổi nguồn, sử dụng phép cộng kiểm tra tràn và giữ trạng thái collector cục bộ. Nếu muốn đánh giá `parallelStream()`, vẫn phải kiểm thử kết quả tương đương và đo hiệu năng với dữ liệu thật.

## 7. Thay Stream.toList() khi baseline là Java 8 hoặc 11

Một lỗi rất thường gặp khi sao chép ví dụ hiện đại:

~~~java
List<String> names = students.stream()
    .map(Student::getName)
    .toList(); // Chỉ có trên Java 16+.
~~~

Nếu baseline là Java 8, 11 hoặc 15, cần dùng collector:

~~~java
List<String> names = students.stream()
    .map(Student::getName)
    .collect(java.util.stream.Collectors.toList());
~~~

**Nhưng đừng cho rằng hai cách hoàn toàn tương đương.**

| API | Mốc | Có thể sửa kết quả? | Chính sách null cần nhớ |
|---|---|---|---|
| `Stream.toList()` | Java 16 | Không thể sửa | Có thể chứa null |
| `Collectors.toList()` | Java 8 | **Không có cam kết** cụ thể về mutability hay kiểu triển khai | Không cam kết cụ thể ngoài hợp đồng của collector |
| `Collectors.toUnmodifiableList()` | Java 10 | Không thể sửa | Từ chối null |
| `Collectors.toCollection(ArrayList::new)` | Java 8 | Trả `ArrayList` mutable | `ArrayList` chấp nhận null |

### 7.1. Khi muốn danh sách có thể sửa trên Java 8

~~~java
List<String> mutable = students.stream()
    .map(Student::getName)
    .collect(java.util.stream.Collectors.toCollection(
        java.util.ArrayList::new
    ));

mutable.add("Sinh viên mới");
~~~

`Collectors.toList()` thường trả một List có thể sửa trong một số triển khai, nhưng **không có bảo đảm API** để dựa vào. Muốn `ArrayList` mutable, chỉ định `toCollection(ArrayList::new)`.

### 7.2. Khi muốn danh sách không thể sửa trên Java 8

~~~java
List<String> collected = students.stream()
    .map(Student::getName)
    .collect(java.util.stream.Collectors.toList());

List<String> readOnly = java.util.Collections.unmodifiableList(
    new java.util.ArrayList<String>(collected)
);

// readOnly.add("X"); // UnsupportedOperationException.
~~~

**Phải sao chép** trước khi bao bằng `unmodifiableList` nếu không muốn view còn phản ánh thay đổi từ một tham chiếu khác đến danh sách gốc. Cách này không tự loại null và không cam kết bất biến sâu của các đối tượng phần tử.

Do đó, khi chuyển từ `Stream.toList()` về Java 8, chọn fallback theo **hợp đồng mutability và null**, không chỉ theo việc code biên dịch thành công.

## 8. List.of, Map.of và copyOf: đừng nhầm với collection cũ

`List.of(...)` và `Map.of(...)` có từ Java 9; `List.copyOf(...)` và `Map.copyOf(...)` có từ Java 10. Chúng tạo các collection không thể sửa (unmodifiable) theo hợp đồng, với chính sách null chặt chẽ.

Trong Java 8:

~~~java
List<String> fixedSize = java.util.Arrays.asList("A", "B");
// fixedSize.add("C"); // UnsupportedOperationException.
// fixedSize.set(0, "X"); // Hợp lệ.

List<String> immutableView =
    java.util.Collections.unmodifiableList(
        new java.util.ArrayList<String>(
            java.util.Arrays.asList("A", "B")
        )
    );
~~~

`Arrays.asList` không tương đương `List.of`: nó tạo List **kích thước cố định** được hỗ trợ bởi mảng và cho phép `set`, đồng thời chấp nhận null. `List.of` không thể sửa và từ chối null.

Nếu cần Map không thể sửa trên Java 8:

~~~java
Map<String, Integer> temp = new java.util.HashMap<String, Integer>();
temp.put("A", 1);
temp.put("B", 2);

Map<String, Integer> readOnlyMap =
    java.util.Collections.unmodifiableMap(
        new java.util.HashMap<String, Integer>(temp)
    );
~~~

Bản sao chỉ bảo vệ cấu trúc Map khỏi sửa qua tham chiếu `temp`; nếu giá trị là đối tượng mutable, cần xem xét **deep immutability** riêng.

## 9. Stream.ofNullable và Optional.stream trên Java 8

Từ Java 9, `Stream.ofNullable(value)` giúp biến một giá trị có thể null thành Stream gồm **0 hoặc 1 phần tử**:

~~~java
String value = null;

long count = java.util.stream.Stream.ofNullable(value)
    .count(); // Java 9+: 0
~~~

Java 8 có thể diễn đạt rõ ràng:

~~~java
static <T> java.util.stream.Stream<T> zeroOrOne(T value) {
    return value == null
        ? java.util.stream.Stream.<T>empty()
        : java.util.stream.Stream.of(value);
}
~~~

Dùng `Stream.of(value)` trực tiếp **không** tương đương: khi `value == null`, biểu thức có thể tạo một Stream chứa **một phần tử null**, thay vì Stream rỗng.

### 9.1. Optional.stream

`Optional.stream()` có từ Java 9. Ví dụ Java 9+:

~~~java
List<java.util.Optional<String>> values =
    java.util.Arrays.asList(
        java.util.Optional.of("A"),
        java.util.Optional.empty(),
        java.util.Optional.of("B")
    );

List<String> present = values.stream()
    .flatMap(java.util.Optional::stream)
    .collect(java.util.stream.Collectors.toList());
~~~

Một cách viết Java 8:

~~~java
List<String> present = values.stream()
    .filter(java.util.Optional::isPresent)
    .map(java.util.Optional::get)
    .collect(java.util.stream.Collectors.toList());
~~~

`Optional.get()` trong ví dụ chỉ được gọi **sau khi lọc `isPresent`**. Với code tổng quát, có thể viết helper dùng `flatMap` và `Stream.empty()/of()` để tránh việc gọi `get` ngoài điều kiện bảo đảm.

Khi review fallback, chú ý cả **Stream rỗng**, **null** và **số lần thực thi callback**; một biến thể ngắn hơn không tự động giữ toàn bộ hợp đồng ban đầu.

## 10. takeWhile và dropWhile khác filter

Từ Java 9, Stream hỗ trợ:

~~~java
stream.takeWhile(predicate)
stream.dropWhile(predicate)
~~~

Trên **Stream có thứ tự**:

- `takeWhile` lấy **tiền tố liên tiếp đầu tiên** thỏa predicate và dừng khi gặp phần tử không thỏa.
- `dropWhile` bỏ **tiền tố liên tiếp đầu tiên** thỏa predicate, sau đó giữ các phần còn lại.

Ví dụ:

~~~java
List<Integer> values = java.util.Arrays.asList(1, 2, 5, 3, 4);

System.out.println(values.stream()
    .takeWhile(n -> n < 4)
    .collect(java.util.stream.Collectors.toList()));
// [1, 2]

System.out.println(values.stream()
    .filter(n -> n < 4)
    .collect(java.util.stream.Collectors.toList()));
// [1, 2, 3]
~~~

**Không thể thay `takeWhile(p)` bằng `filter(p)` nói chung**, vì `filter` có thể giữ các phần tử thỏa điều kiện xuất hiện **sau** phần tử không thỏa đầu tiên.

### 10.1. Java 8: chọn thuật toán khác nếu cần dừng tại phần tử đầu không đạt

Với dữ liệu trong List và yêu cầu tuần tự:

~~~java
List<Integer> prefix = new java.util.ArrayList<Integer>();

for (Integer value : values) {
    if (value >= 4) {
        break;
    }
    prefix.add(value);
}

System.out.println(prefix); // [1, 2]
~~~

Một vòng `for` rõ ý nghĩa hơn một `filter` sai. Nếu dự án cần hỗ trợ lười (*lazy*) hoặc nguồn I/O, có thể tự triển khai Iterator/Spliterator có điểm dừng, nhưng phải quản lý quyền sở hữu tài nguyên và ngữ nghĩa `trySplit` rất cẩn thận.

### 10.2. iterate ba tham số

`Stream.iterate(seed, hasNext, next)` có từ Java 9 và giúp tạo dãy hữu hạn theo điều kiện:

~~~java
java.util.stream.IntStream.iterate(0, n -> n < 5, n -> n + 1)
    .forEach(System.out::println); // Java 9+
~~~

Với dãy số học đơn giản, Java 8 có thể chọn `IntStream.range(0, 5)`. Nhưng với bộ sinh có bước tiếp theo phụ thuộc trạng thái hoặc điều kiện kết thúc phức tạp, không thể thay thế máy móc bằng `range`; cần thiết kế lại nguồn theo đúng ngữ nghĩa.

## 11. Collectors.filtering và flatMapping: fallback phải giữ nghĩa của nhóm

Từ Java 9, `Collectors.filtering` và `Collectors.flatMapping` có thể được dùng **bên trong downstream collector**.

Ví dụ muốn giữ cả nhóm có doanh thu thành công bằng 0:

~~~java
Map<String, Long> paidCountByRegion = payments.stream()
    .collect(java.util.stream.Collectors.groupingBy(
        Payment::getRegion,
        java.util.stream.Collectors.filtering(
            Payment::isPaid,
            java.util.stream.Collectors.counting()
        )
    ));
~~~

`Payment` ở đây là kiểu dữ liệu Java có phương thức `getRegion()` và `isPaid()`, ví dụ như chương trình mục 6. Cách viết trên cần Java 9+.

Nếu chuyển điều kiện sang trước khi nhóm:

~~~java
payments.stream()
    .filter(Payment::isPaid)
    .collect(java.util.stream.Collectors.groupingBy(
        Payment::getRegion,
        java.util.stream.Collectors.counting()
    ));
~~~

thì nhóm **không có khoản thanh toán thành công** biến mất hoàn toàn. Đây **không** là fallback tương đương nếu yêu cầu phải hiển thị nhóm với count = 0.

### 11.1. Java 8 fallback cho trường hợp chỉ cần đếm

~~~java
Map<String, Long> paidCountByRegion = payments.stream()
    .collect(java.util.stream.Collectors.groupingBy(
        Payment::getRegion,
        java.util.stream.Collectors.summingLong(
            p -> p.isPaid() ? 1L : 0L
        )
    ));
~~~

Tất cả khoản thanh toán được đưa đến `groupingBy`; giá trị tích lũy của mỗi phần tử là 1 nếu đạt điều kiện và 0 nếu không. Vì vậy, một khu vực có dữ liệu nhưng toàn khoản chưa thanh toán **vẫn có khóa với số đếm 0**.

Fallback này giữ nghĩa **cho bài toán đếm**. Nó không thay thế tổng quát mọi `Collectors.filtering(predicate, downstream)` hoặc một `flatMapping` tùy ý. Khi yêu cầu phức tạp hơn, cần viết downstream collector tương thích hoặc thay đổi thiết kế một cách có kiểm soát.

### 11.2. Khi cần flatMapping

`Collectors.flatMapping(mapper, downstream)` (Java 9+) cho phép từ một phần tử của **một nhóm** phát ra 0..n giá trị để downstream thu lại. Ở Java 8, có thể dùng collector tự viết hoặc thu trung gian trong từng nhóm rồi xử lý tiếp, nhưng phương án thu List sẽ tăng bộ nhớ.

**Không dời `flatMap` ra trước `groupingBy` nếu thao tác đó làm mất khóa nhóm hoặc thay đổi cách gán phần tử vào nhóm.** Đây là vấn đề tương thích **ngữ nghĩa**, không chỉ khác phiên bản API.

## 12. teeing trên Java 12 và collector thay thế từ Java 8

`Collectors.teeing(downstream1, downstream2, merger)` (Java 12+) đưa mỗi phần tử cho **hai downstream collector**, rồi gọi merger để ghép hai kết quả.

Ví dụ nếu chỉ cần số lượng và tổng tiền của **mọi khoản thanh toán**:

~~~java
// Java 12+. Payment và Report là các lớp trong ví dụ mục 6.
java.util.Map.Entry<Long, Long> pair = payments.stream()
    .collect(java.util.stream.Collectors.teeing(
        java.util.stream.Collectors.counting(),
        java.util.stream.Collectors.summingLong(Payment::getAmountVnd),
        (count, total) ->
            new java.util.AbstractMap.SimpleImmutableEntry<Long, Long>(
                count, total
            )
    ));
~~~

Ở Java 8, `teeing` chưa tồn tại. Nếu hai giá trị cùng thuộc một trường số, có thể dùng `summarizingLong`:

~~~java
java.util.LongSummaryStatistics summary = payments.stream()
    .collect(java.util.stream.Collectors.summarizingLong(
        Payment::getAmountVnd
    ));

System.out.println(summary.getCount());
System.out.println(summary.getSum());
~~~

Nếu cần nhiều phép thu thập không cùng bản chất, có thể viết **collector tùy chỉnh** với supplier, accumulator, combiner, finisher như `MutableReport` trong mục 6. Làm như vậy **không** yêu cầu duyệt lại nguồn và vẫn hỗ trợ chia/gộp theo hợp đồng.

### 12.1. Đừng sử dụng reduce với một ArrayList dùng chung để “bù” teeing

Một cách viết sai là gọi `reduce(new ArrayList<>(), accumulatorMutating, combiner)` rồi chỉnh sửa chính identity trong accumulator. Cách này vi phạm mô hình non-mutating reduction và có thể sai khi chạy song song.

Khi xây báo cáo tích lũy mutable, hãy dùng `collect` hoặc `Collector.of`. Để có kết quả bất biến, dùng finisher tạo **bản sao độc lập** thay vì đưa thẳng container mutable trung gian ra bên ngoài.

### 12.2. Có cần tăng baseline chỉ để dùng teeing?

Không nhất thiết. Nếu dự án chỉ có vài phép cộng/đếm, collector Java 8 hoặc `summarizingLong` có thể đơn giản hơn. Nhưng nếu nhiều báo cáo phức hợp thường xuyên ghép hai downstream có sẵn, Java 12+ có thể cải thiện đáng kể khả năng diễn đạt.

Quyết định nên dựa trên **mức JDK deployment được phép**, số lượng nơi cần fallback và chi phí bảo trì, chứ không chỉ số dòng code.

## 13. mapMulti: API mới và phương án flatMap cũ

`Stream.mapMulti` có từ Java 16, dùng khi một phần tử cần phát **không, một hoặc nhiều** phần tử đầu ra. Trên Java 8, cách phổ biến là `flatMap`.

Ví dụ Java 8: tách các chuỗi bằng dấu phẩy rồi chỉ giữ phần không rỗng.

~~~java
List<String> parts = java.util.Arrays.asList(
    "java,stream", "", "collector,api"
);

List<String> tokens = parts.stream()
    .flatMap(line -> java.util.Arrays.stream(line.split(",")))
    .filter(token -> !token.isEmpty())
    .collect(java.util.stream.Collectors.toList());

System.out.println(tokens); // [java, stream, collector, api]
~~~

Từ Java 16 có thể diễn đạt qua `mapMulti`:

~~~java
List<String> tokens = parts.stream()
    .<String>mapMulti((line, downstream) -> {
        for (String token : line.split(",")) {
            if (!token.isEmpty()) {
                downstream.accept(token);
            }
        }
    })
    .toList();
~~~

Hai đoạn có cùng kết quả với dữ liệu mẫu. `mapMulti` có thể tránh việc tạo một Stream trung gian cho mỗi phần tử như cách viết `flatMap`, nhưng **không được khẳng định luôn nhanh hơn** mà không đo trên workload thực tế.

Đây là ví dụ nâng cấp khi runtime cho phép; nếu phải giữ Java 8, `flatMap` vẫn diễn đạt tốt bài toán.

## 14. Stream Gatherers và giới hạn baseline Java 24

**Stream Gatherers** mở rộng khả năng tạo thao tác trung gian có trạng thái và cấu trúc xử lý phức tạp, như quét tích lũy, cửa sổ cố định/trượt hoặc tích hợp một số mô hình xử lý đồng thời.

Điểm tương thích:

- Java **22 và 23** có phiên bản **preview**, nên phải xem xét cơ chế bật preview tương ứng và các thay đổi có thể xảy ra.
- **Java 24** là phiên bản mà `Stream.gather`, `Gatherer` và `Gatherers` trở thành API **chuẩn**, không còn yêu cầu bật preview chỉ để dùng các API này.
- Nếu runtime tối thiểu là Java 8, 11, 17 hoặc 21, **không thể gọi trực tiếp Gatherers chuẩn** trong phần mã bắt buộc chạy trên runtime đó.

Ví dụ minh họa **Java 24+**:

~~~java
import java.util.List;
import java.util.stream.Gatherers;

public class GathererWindowDemo {
    public static void main(String[] args) {
        List<List<Integer>> windows = List.of(1, 2, 3, 4, 5)
            .stream()
            .gather(Gatherers.windowFixed(2))
            .toList();

        System.out.println(windows);
        // [[1, 2], [3, 4], [5]]
    }
}
~~~

Đây là ví dụ tính năng mới, **không được đưa vào module phải biên dịch với `--release 17` hoặc `--release 8`**.

### 14.1. Fallback phải xét vị trí trong pipeline

Gatherer là **intermediate operation**. Một phép `collect` thông thường là **terminal operation**; do vậy không phải gatherer nào cũng thay bằng collector mà giữ nguyên khả năng tiếp tục `filter`/`map` ở phía sau.

Nếu yêu cầu chỉ chia **một List hữu hạn** thành các lô cố định trên Java 8, một vòng lặp tạo bản sao từng đoạn thường dễ hiểu và dễ kiểm chứng:

~~~java
static <T> List<List<T>> batches(List<T> source, int batchSize) {
    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize phải dương");
    }

    List<List<T>> result = new java.util.ArrayList<List<T>>();

    for (int from = 0; from < source.size(); from += batchSize) {
        int to = Math.min(source.size(), from + batchSize);
        result.add(new java.util.ArrayList<T>(
            source.subList(from, to)
        ));
    }

    return result;
}
~~~

Phương thức trên có **đầu vào List hữu hạn**, trả toàn bộ các lô vào bộ nhớ và không lazy như một nguồn Stream. Nó cũng cần xem xét tràn số khi cộng `from + batchSize` nếu kích thước/giới hạn có thể cực lớn; có thể thiết kế phép tính `to` bằng hiệu để bảo vệ hoàn toàn.

Với bài toán bắt buộc **lazy** hoặc xử lý streaming theo cửa sổ, cần một Iterator/Spliterator hay thao tác trung gian khác được thiết kế theo hợp đồng, không đơn giản coi vòng lặp trên List là bản thay thế hoàn toàn.

### 14.2. Tránh preview trong phần core nếu baseline yêu cầu ổn định

API preview có thể thay đổi hoặc bị rút lại trước khi chuẩn hóa. Nếu dự án cần xây dựng thư viện phát hành lâu dài cho nhiều môi trường, nên:

1. Cô lập phần thử nghiệm trong module/ứng dụng riêng.
2. Ghi rõ phiên bản preview và cờ build/runtime.
3. Không coi artifact preview là binary tương thích xuyên nhiều bản JDK.
4. Khi API chuẩn được phát hành, kiểm tra lại mã nguồn, chữ ký API và kiểm thử, không chỉ bỏ cờ preview.

## 15. Không phải khác biệt nào cũng do phiên bản JDK

Một pipeline có thể biên dịch trên cả Java 8 và Java 17 nhưng khác **ngữ nghĩa** nếu thay đổi API một cách máy móc.

### 15.1. Rỗng và Optional

~~~java
java.util.Optional<Integer> max =
    java.util.stream.Stream.of(2, 4, 3)
        .max(Integer::compareTo);
~~~

`max` trả `Optional` trên Java 8 trở lên vì nguồn có thể rỗng. Nếu viết mã cho Java 8, không nên đổi sang `max.get()` chỉ để rút ngắn; phải xử lý trường hợp `Optional.empty()`.

### 15.2. Primitive stream và boxing

~~~java
long total = java.util.stream.IntStream.range(0, 100)
    .asLongStream()
    .sum();
~~~

`IntStream`, `LongStream` và `DoubleStream` đã tồn tại từ Java 8; không cần nâng JDK chỉ để tránh boxing trong phép cộng đơn giản. `mapToLong`/`asLongStream` thường biểu diễn bài toán số học rõ ràng.

### 15.3. Thứ tự và collector

`Collectors.toSet()` không bảo đảm thứ tự duyệt; `groupingBy(...)` không cam kết Map triển khai cụ thể; `findAny()` không phải cách chọn phần tử đầu. Đó là **hợp đồng API đã có từ Java 8**, không phải điểm thay đổi chỉ do nâng JDK.

Khi thay bản triển khai để tương thích, phải giữ các thuộc tính mà nghiệp vụ thật sự cần: thứ tự, khả năng sửa, null, equality, trình tự kết hợp và tài nguyên.

### 15.4. Parallel và trạng thái

Một code chạy tuần tự đúng trên Java 8 có thể sai trên chính Java 8 khi thêm `parallel()` nếu accumulator dùng trạng thái ngoài. Tăng phiên bản JDK cũng không tự sửa race condition, phép `reduce` không associative hay việc dùng chung `ArrayList`.

Hãy kiểm tra **tính đúng trước khi benchmark**, nhất là khi thay pipeline để tận dụng khả năng phân chia của `Spliterator` hoặc collector đồng thời.

## 16. Tương thích tài nguyên: Files.lines và try-with-resources

`Files.lines(Path, Charset)` đã có từ Java 8, tạo Stream từ tệp và cần đóng khi không dùng nữa.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

Path path = Paths.get("payments.txt"); // Tương thích Java 8.

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long rows = lines
        .filter(line -> !line.trim().isEmpty())
        .count();

    System.out.println(rows);
}
~~~

Code này không dùng `Path.of` (Java 11) hoặc `String.isBlank` (Java 11). Nó chạy với Java 8 nếu tệp tồn tại và runtime có quyền truy cập.

**Nhưng `trim().isEmpty()` không hoàn toàn tương đương `isBlank()` theo mọi ký tự Unicode.** Nếu dự án chuyển giữa hai cách xử lý để hạ baseline, phải quyết định rõ định nghĩa “dòng trắng” và kiểm thử các loại whitespace thực tế.

### 16.1. Terminal operation không tự đóng nguồn I/O

`count()`, `findFirst()`, `collect()` không tự đóng Stream do `Files.lines` tạo. Quyền sở hữu tài nguyên cần thể hiện qua `try-with-resources`.

`onClose` (Java 8) chỉ **đăng ký callback khi đóng**, không tự đóng sau khi terminal operation chạy xong. Khi hạ baseline, đừng thay khối quản lý tài nguyên bằng việc gọi `onClose` rồi cho rằng đã xử lý xong.

### 16.2. Nếu nguồn quá lớn

Dù dùng JDK mới, một terminal `collect(toList())` có thể đưa toàn bộ nội dung vào bộ nhớ. `Stream` lazy không đồng nghĩa bộ nhớ kết quả không giới hạn. Nếu chỉ cần đếm/tổng, ưu tiên collector tổng hợp hoặc xử lý theo lô.

Bài toán I/O, bộ nhớ, giới hạn xử lý và thời gian không được giải quyết chỉ bằng cách nâng JDK hay bật `parallelStream()`.

## 17. Maven, Gradle và toolchain: khai báo ý định ở build

**Mục tiêu:** mọi môi trường CI và máy phát triển phải cùng hiểu mức Java được phép sử dụng.

### 17.1. Maven

Một cấu hình Maven điển hình cho module Java 8 khi build bằng JDK hỗ trợ `--release`:

~~~xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
~~~

Cần sử dụng phiên bản **Maven Compiler Plugin** có hỗ trợ cấu hình `release` và phiên bản JDK chạy Maven phù hợp. Nếu build bằng chính JDK 8, `javac` của Java 8 **không có `--release`**; lúc đó cần cấu hình build/toolchain thích hợp cho môi trường đó thay vì giả định thuộc tính trên hoạt động giống hệt ở mọi phiên bản plugin/JDK.

Trong dự án multi-module, có thể cấu hình release khác nhau cho những module được phép dùng API mới, nhưng phải tránh để module baseline cũ vô tình phụ thuộc module đã biên dịch với class version mới hơn.

### 17.2. Gradle

Ví dụ minh họa **Gradle Groovy DSL** dùng toolchain và cấu hình mức bytecode/API mục tiêu:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
}
~~~

Ý nghĩa: dùng compiler từ JDK 17 theo toolchain, nhưng yêu cầu phát hành code tương thích Java 8. Tùy phiên bản Gradle, plugin và toolchain, cần kiểm tra hỗ trợ thực tế trước khi áp dụng nguyên mẫu. **Toolchain JDK 17 không đồng nghĩa runtime triển khai tối thiểu cũng là 17** nếu mức `release` của code và phụ thuộc thực sự được giữ ở 8.

### 17.3. Không trộn lẫn source level với runtime của test

Nếu compile bằng JDK 17 với `--release 8` rồi chỉ chạy unit test trên Java 17, bạn **chưa kiểm chứng** rằng toàn bộ dependency và nhánh runtime hoạt động trên Java 8. Bản build vượt qua phép kiểm tra API nền tảng, nhưng kiểm thử runtime tối thiểu vẫn cần thiết.

Đối với thư viện phát hành cho người khác, ghi rõ các phiên bản runtime được hỗ trợ trong tài liệu và kiểm tra trên từng runtime đó theo khả năng của hệ thống CI.

## 18. Dependencies: giới hạn thường bị bỏ sót

Giả sử mã nguồn ứng dụng chỉ dùng các API Java 8, nhưng một dependency đã được biên dịch cho Java 17. Ứng dụng có thể **không nạp được class của dependency** trên Java 8, kể cả khi source của ứng dụng vẫn pass `--release 8`.

Các rủi ro cần kiểm tra:

| Nhóm phụ thuộc | Vấn đề có thể gặp |
|---|---|
| JAR bên thứ ba | Class file biên dịch từ phiên bản Java cao hơn |
| Thư viện gọi API mới | `NoSuchMethodError`/`NoClassDefFoundError` ở runtime cũ |
| Annotation processor | Yêu cầu JDK build cao hơn, khác runtime mục tiêu |
| Java agent | Hook vào JVM và JDK internals có thể thay đổi |
| JNI/native library | Phụ thuộc OS/kiến trúc và ABI, không chỉ Java |
| Framework/server | Có baseline Java riêng hoặc yêu cầu module/JVM flag khác |
| Test tool | Có thể chạy được trên JDK build nhưng không hỗ trợ runtime thử nghiệm |
| Reflection/internal APIs | Có thể bị giới hạn bởi mô hình module và encapsulation của JDK mới |

Vì vậy, xác định JDK tối thiểu là việc của **toàn ứng dụng và chuỗi phụ thuộc**, không chỉ một file Java.

### 18.1. Nhận biết class version

Một số mốc class file hay dùng khi chẩn đoán:

| Phiên bản Java | Class file major version |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 24 | 68 |

Trình biên dịch phát ra class file tương ứng với target release, nhưng bản thân con số major **không chứng minh API hoặc dependency tương thích hoàn toàn**. Có thể dùng `javap -verbose` để kiểm tra metadata của class đã biên dịch, rồi vẫn phải chạy test trên JVM mục tiêu.

## 19. Khi cần hai cách triển khai cho hai baseline

Không phải dự án nào cũng có thể nâng đồng loạt. Một hệ thống có thể có:

- **Core library** hỗ trợ Java 8 để tích hợp với khách hàng cũ.
- **Service mới** chạy Java 17 hoặc cao hơn.
- **Module thử nghiệm** dùng Gatherers trên Java 24+.

Cách tiếp cận thường an toàn là định nghĩa một **hợp đồng đầu ra chung**, rồi lựa chọn triển khai theo module/runtime riêng.

~~~text
                      Hợp đồng Report
                             |
                 +-----------+-----------+
                 |                       |
          Core Java 8             Adapter Java mới
         Collector.of(...)        teeing / Gatherers
                 |                       |
                 +----------+------------+
                            |
                  Kiểm thử kết quả chung
~~~

Quan trọng:

1. Interface và kiểu dữ liệu dùng chung **không** được tham chiếu kiểu chỉ tồn tại trên JDK mới nếu core phải nạp được trên JDK cũ.
2. Module Java 8 không được phụ thuộc trực tiếp class chỉ biên dịch cho Java 17/24.
3. Dù hai cách triển khai khác nhau, yêu cầu null, thứ tự, kết quả rỗng, số học và lỗi phải được kiểm thử tương đương.
4. Việc chọn triển khai theo runtime nên được cách ly và tài liệu hóa; tránh gọi API mới từ những class luôn được nạp ở runtime cũ.

**Multi-release JAR** (từ Java 9) là một kỹ thuật đóng gói biến thể class theo phiên bản runtime, nhưng làm tăng chi phí build/test và không thay thế thiết kế ranh giới API rõ ràng. Chỉ nên chọn khi thật sự có lý do về tương thích và bảo trì.

## 20. Ma trận kiểm thử tính tương thích

Một dự án tuyên bố “hỗ trợ Java 8, 11, 17 và 21” cần bằng chứng trên các runtime đó, không chỉ một lần build thành công.

| Bước | Java thấp nhất | Java cao hơn | Mục đích |
|---|---|---|---|
| Kiểm tra cú pháp/API bằng `--release` | Target 8 | Compiler hỗ trợ release 8 | Ngăn dùng API Java 9+ ngoài ý muốn |
| Build dependency | Theo baseline | Theo phiên bản các thư viện | Phát hiện bytecode mới lọt vào artifact |
| Unit test | Chạy trên 8 | Chạy thêm 11/17/21 nếu hỗ trợ | Kiểm tra đường code và hợp đồng API |
| Integration test | Chạy với môi trường thực | Chạy thêm môi trường nâng cấp | Phát hiện I/O, reflection, TLS, framework, native |
| Kiểm thử dữ liệu rỗng/null/lỗi | Có | Có | Tránh khác biệt ngữ nghĩa fallback |
| Kiểm thử parallel | Có nếu dùng | Có nếu dùng | Kiểm tra order, accumulator, combiner, race |
| Hiệu năng | Dữ liệu đại diện | Dữ liệu đại diện | So sánh sau khi đúng, không chỉ đo thời gian đơn lẻ |

### 20.1. Các ca kiểm thử tối thiểu cho chương trình mục 6

1. **Nguồn rỗng:** trả count = 0, total = 0 và Map rỗng.
2. **Tất cả `paid = false`:** trả báo cáo tương tự rỗng, nhưng nguồn vẫn có phần tử.
3. **Dữ liệu mẫu:** count = 3, total = 250.000, North = 200.000, South = 50.000.
4. **Một khu vực mới:** có khóa mới với tổng chính xác.
5. **Số tiền âm:** constructor từ chối.
6. **Tổng vượt `long`:** `Math.addExact` ném `ArithmeticException`, không lặng lẽ tràn.
7. **Map báo cáo:** không cho phép `put` qua getter.
8. **Sequential vs parallel (khi thử):** báo cáo bằng nhau trên dữ liệu bất biến.
9. **Runtime thấp nhất:** chạy được artifact đã build cùng toàn bộ dependencies cần thiết.

Nếu một ca chưa có chính sách nghiệp vụ (ví dụ giao dịch trùng ID), ghi nhận là **chưa xác định**, không tự đánh dấu PASS chỉ vì test hiện tại không chứa dữ liệu trùng.

### 20.2. Kiểm thử regression khi nâng baseline

Khi chuyển từ Java 8 sang 17, việc thay `collect(toList())` bằng `toList()` có thể khiến code **đang sửa List kết quả** ném `UnsupportedOperationException`. Tương tự, chuyển từ Map/List có thể sửa sang `copyOf` có thể từ chối null.

Vì vậy, test nên xác định:

- Caller có được sửa collection kết quả hay không.
- Null được giữ, loại hay báo lỗi.
- Thứ tự kết quả có phải một phần contract hay không.
- Kết quả trên nguồn rỗng, số lớn, dữ liệu có giá trị trùng.
- Kết quả khi xử lý song song và thao tác I/O.

Đây là những thay đổi có thể **hợp lệ về mặt biên dịch** nhưng phá hợp đồng nghiệp vụ.

## 21. Bài tập 1 — tìm JDK tối thiểu từ một đoạn code

Xét chương trình:

~~~java
record Item(String code, long amount) {}

List<Item> items = List.of(
    new Item("A", 100L),
    new Item("B", 200L)
);

List<String> codes = items.stream()
    .map(Item::code)
    .toList();
~~~

**Câu hỏi:** JDK tối thiểu để biên dịch chương trình này với các API/cú pháp chuẩn, không dùng preview, là bao nhiêu?

**Phân tích:**

- `List.of`: Java 9.
- `record` chính thức: Java 16.
- `Stream.toList`: Java 16.
- `Stream.map`: Java 8.

Mốc cao nhất là **Java 16**. Bản thân code không bắt buộc Java 17 chỉ vì người viết thường dùng JDK 17.

### 21.1. Viết lại cho Java 8

~~~java
final class Item {
    private final String code;
    private final long amount;

    Item(String code, long amount) {
        this.code = code;
        this.amount = amount;
    }

    String getCode() { return code; }
    long getAmount() { return amount; }
}

// Sử dụng bên trong một phương thức:
List<Item> items = java.util.Arrays.asList(
    new Item("A", 100L),
    new Item("B", 200L)
);

List<String> codes = items.stream()
    .map(Item::getCode)
    .collect(java.util.stream.Collectors.toList());
~~~

Bản Java 8 vẫn tạo cùng **danh sách mã** với đầu vào mẫu. Nhưng tính bất biến của `List.of` và `Stream.toList` đã thay đổi; nếu nghiệp vụ cần List không thể sửa, phải thêm lớp bảo vệ đầu ra và kiểm thử theo mục 7–8.

## 22. Bài tập 2 — chọn fallback giữ nhóm có giá trị 0

**Yêu cầu:** một báo cáo phải hiển thị **mọi khu vực đã có giao dịch**, kể cả khu vực không có khoản thanh toán thành công, với số đếm bằng 0.

Phiên bản Java 9+:

~~~java
Map<String, Long> counts = payments.stream()
    .collect(java.util.stream.Collectors.groupingBy(
        Payment::getRegion,
        java.util.stream.Collectors.filtering(
            Payment::isPaid,
            java.util.stream.Collectors.counting()
        )
    ));
~~~

**Nhiệm vụ:** viết lại trên Java 8 và giải thích vì sao không chỉ `filter` trước nhóm.

**Lời giải:**

~~~java
Map<String, Long> counts = payments.stream()
    .collect(java.util.stream.Collectors.groupingBy(
        Payment::getRegion,
        java.util.stream.Collectors.summingLong(
            payment -> payment.isPaid() ? 1L : 0L
        )
    ));
~~~

Nhóm được tạo trước khi tính 1 hay 0, nên nhóm có dữ liệu nhưng không có khoản `paid` vẫn xuất hiện. Nếu `stream.filter(Payment::isPaid)` được đặt trước grouping, nhóm chỉ có giao dịch chưa thanh toán sẽ **không có khóa**.

Fallback này chỉ thay thế đúng ngữ nghĩa của phép **đếm phần tử đạt điều kiện**; với các downstream phức tạp hơn, phải phân tích lại.

## 23. Bài tập 3 — lập quyết định hỗ trợ JDK cho dự án

Giả sử một thư viện báo cáo Stream được khách hàng sử dụng ở ba môi trường:

- Khách hàng A: runtime bắt buộc **Java 8**.
- Khách hàng B: runtime **Java 17**.
- Một dịch vụ nội bộ: muốn thử **Gatherers chuẩn**.

**Yêu cầu:**

1. Xác định mức Java tối thiểu của artifact dùng chung cho A và B.
2. Xác định module nào có thể dùng `teeing` trực tiếp.
3. Chỉ ra cách thử Gatherers mà không làm thư viện dùng chung không chạy được trên Java 8.
4. Đề xuất kiểm thử bắt buộc trước khi phát hành.
5. Nêu trường hợp nào nên đề xuất nâng baseline thay vì viết thêm fallback.

### Gợi ý lời giải

**Artifact dùng chung** phải tiếp tục hỗ trợ **Java 8**, nếu yêu cầu dành cho A vẫn còn hiệu lực. Nó không thể công khai kiểu hoặc lời gọi API chỉ có ở JDK mới trong phần code A phải nạp.

**Dịch vụ Java 17** có thể sử dụng `Collectors.teeing` và `Stream.toList` trong module riêng mà chỉ chạy ở Java 17, miễn không làm tăng mức class file/API của artifact dùng chung.

**Gatherers chuẩn** đòi hỏi Java 24+, nên thử ở module hoặc ứng dụng nội bộ chạy runtime phù hợp, độc lập với artifact baseline 8. Giữ hợp đồng đầu ra hoặc mô hình dữ liệu chung ở dạng mà module Java 8 có thể hiểu.

**Ma trận test** cần ít nhất một lượt chạy trên Java 8 cho thư viện core, thêm runtime Java 17 cho service, và môi trường Java 24+ cho nhánh Gatherers. Những lớp giao tiếp giữa các phần cần test tương thích kiểu, dữ liệu rỗng, lỗi và thứ tự.

**Nâng baseline** hợp lý nếu chi phí bảo trì cách triển khai cũ quá cao, khách hàng đã có kế hoạch nâng runtime, hoặc có ràng buộc hỗ trợ/bảo mật đòi hỏi thay đổi. Việc này cần quyết định sản phẩm và vận hành; không nên do một refactor Stream đơn lẻ tự quyết.

## 24. Các lỗi tương thích thường gặp

| Sai lầm | Vì sao gây vấn đề | Cách xử lý |
|---|---|---|
| Dùng `Stream.toList()` trong code phải chạy trên Java 11 | API chỉ có từ Java 16 | Dùng collector Java 8 phù hợp và xét mutability |
| Dùng `Collectors.teeing` khi target 8 | API chỉ có từ Java 12 | Dùng collector Java 8 hoặc `summarizingLong` |
| Dùng `List.of` rồi đổi thẳng sang `Arrays.asList` | Mutability/null khác nhau | Tạo bản sao và wrapper nếu cần |
| Thay `takeWhile` bằng `filter` | Có thể thay đổi tập kết quả | Dùng vòng lặp dừng sớm hoặc nguồn custom |
| Dùng `String.isBlank` trong module `--release 8` | API chỉ có từ Java 11 | Xác định chính sách blank và dùng cách tương thích |
| Dùng `Path.of` trong Java 8 | `Path.of` có từ Java 11 | Dùng `Paths.get` |
| Dùng `record` trong source level 8 | Cú pháp chưa được hỗ trợ | Dùng class thường |
| Chỉ cấu hình `-source/-target` rồi cho rằng API cũng bị giới hạn | Có thể lọt lời gọi API mới | Ưu tiên `--release` |
| Chỉ test trên JDK build cao | Không thấy lỗi của runtime cũ | Test trên runtime thấp nhất |
| Không kiểm tra class version của dependencies | Library có thể không nạp được | Quản lý dependency baseline |
| Đưa preview API vào thư viện core ổn định | Phụ thuộc bản preview có thể thay đổi | Cô lập module thử nghiệm |
| Tin rằng nâng JDK tự sửa lỗi parallel | Race, side effect và combiner sai vẫn tồn tại | Kiểm thử hợp đồng độc lập với phiên bản |
| Không xác định ai đóng `Files.lines` | Leak file descriptor/tài nguyên | `try-with-resources`, ownership rõ ràng |
| Thay `toList` bằng collector rồi giả định collection có thể sửa | API không cam kết mutability | Dùng `toCollection(ArrayList::new)` khi cần |
| Cho rằng `--release` kiểm hết tương thích của hệ thống | Không kiểm tra mọi dependency/native/environment | Thực thi test tích hợp trên runtime đích |

## 25. Checklist trước khi chốt JDK tối thiểu

| Câu hỏi kiểm tra | Bằng chứng nên có |
|---|---|
| Môi trường runtime thấp nhất là phiên bản nào? | Danh sách phiên bản sản phẩm cam kết hỗ trợ |
| Đã phân biệt compiler JDK và runtime JDK? | Log `java -version`, `javac -version` |
| Mỗi API/cú pháp mới có mốc tối thiểu rõ? | Bảng các API đang sử dụng |
| Build đã ràng buộc source, API và bytecode? | Cấu hình `--release` hoặc toolchain tương ứng |
| Có dependency yêu cầu Java mới hơn không? | Dependency audit, class version, tài liệu thư viện |
| Fallback có giữ null/mutability/order/empty semantics? | Unit test trên dữ liệu biên |
| Có API preview hoặc JDK-internal không? | Danh mục rủi ro và kế hoạch nâng cấp |
| Có dùng nguồn I/O với quyền sở hữu rõ? | `try-with-resources` và test lỗi |
| Có dùng parallel hoặc custom Spliterator đúng hợp đồng? | Test kết quả, race, split/estimate và combiner |
| Test đã chạy trên runtime tối thiểu? | CI job và artifact log |
| Có test trên phiên bản JDK cao hơn được hỗ trợ? | Ma trận test đa phiên bản |
| Benchmark chỉ thực hiện sau khi code đúng? | Kết quả test và báo cáo hiệu năng |
| Lịch hỗ trợ/bảo mật của runtime đã được xác minh? | Chính sách nhà cung cấp và kế hoạch nâng cấp |

## 26. Câu hỏi tự kiểm tra

1. `Stream` và `Collectors.groupingBy` có từ Java nào? — **Java 8**.
2. `Stream.toList()` có từ Java nào? — **Java 16**.
3. `Collectors.teeing` có từ Java nào? — **Java 12**.
4. `Stream.ofNullable` và `Optional.stream` có từ Java nào? — **Java 9**.
5. `Collectors.toUnmodifiableList` có từ Java nào? — **Java 10**.
6. `Stream.mapMulti` có từ Java nào? — **Java 16**.
7. `Stream.gather` và Gatherers chuẩn cần Java nào? — **Java 24 trở lên**.
8. `record` chính thức ở Java nào? — **Java 16**.
9. Dùng JDK 17 để build có bắt buộc runtime tối thiểu là Java 17 không? — **Không**, nếu biên dịch và phụ thuộc được ràng buộc về release thấp hơn đúng cách.
10. Vì sao `--release 8` hữu ích hơn chỉ `-source 8 -target 8`? — Vì nó còn kiểm soát **API nền tảng Java** được phép gọi.
11. `--release` có bảo đảm mọi JAR bên thứ ba chạy được trên Java 8 không? — **Không**.
12. `Arrays.asList` có tương đương `List.of` không? — **Không**, khác chính sách sửa và null.
13. `Collectors.toList` có bảo đảm List mutable không? — **Không**.
14. Vì sao `takeWhile(p)` không thể thay máy móc bằng `filter(p)`? — Vì một bên lấy **tiền tố liên tiếp**, một bên giữ **mọi phần tử thỏa điều kiện**.
15. `Collectors.filtering` trong `groupingBy` có thể khác `stream.filter` ở đâu? — **Khả năng giữ nhóm có count 0**.
16. Một Stream từ `Files.lines` có tự đóng sau `count` không? — **Không**, cần quản lý đóng nguồn.
17. Vì sao parallel Stream không tự nhanh hơn khi nâng JDK? — Vì còn kích thước nguồn, chi phí, cách chia, order và combiner.
18. Nếu mã dùng `Stream.toList()` và `record`, mốc tối thiểu không preview là gì? — **Java 16**.
19. Khi nào nên chọn collector tùy chỉnh Java 8 thay vì `teeing`? — Khi baseline cũ bắt buộc và hợp đồng thu thập cần gộp nhiều kết quả trong một lượt duyệt.
20. Một dự án tương thích thật cần bước cuối nào? — **Chạy kiểm thử trên runtime thấp nhất cùng dependencies thực tế**.

## 27. Tổng kết: tương thích là một hợp đồng, không phải một cờ compiler

Để xác định **JDK tối thiểu**, trước tiên hãy xét **runtime phải hỗ trợ**, sau đó lập danh sách **tính năng ngôn ngữ**, **API chuẩn**, **dependency** và **công cụ build**. Cấu hình `javac --release` giúp bảo vệ mốc API/bytecode, nhưng không thay thế kiểm thử trên runtime thật.

Khi muốn dùng một API Stream mới, hãy hỏi:

- Có thực sự cần nó, hay API Java 8 đã giải quyết bài toán đủ rõ và đúng?
- Nếu dùng fallback, có giữ đúng **null**, **kết quả rỗng**, **mutability**, **thứ tự** và **quy tắc nhóm** không?
- Nếu nâng baseline, có ảnh hưởng khách hàng, deployment, CI hay thư viện bên thứ ba không?
- Nếu dùng preview/Gatherers hoặc xử lý song song, có bằng chứng về tính đúng, vòng đời tài nguyên và hiệu năng không?

Tính tương thích tốt không có nghĩa luôn giữ JDK cũ nhất hay chạy theo JDK mới nhất. Đó là việc **chọn phiên bản tối thiểu có căn cứ, thiết kế fallback có ngữ nghĩa rõ ràng và kiểm chứng bằng build/test thực tế**. Nguyên tắc này giúp các dự án Java Stream API dùng `filter`, `map`, `reduce`, `collect`, grouping, `Spliterator`, parallel Stream và Stream Gatherers một cách bền vững, dễ bảo trì và đáng tin cậy.
