# ClassLoadingMXBean và số lớp được nạp

## 1. Vì sao giám sát việc nạp lớp?

Một ứng dụng Java không nhất thiết nạp mọi lớp ngay khi khởi động. Thư viện, trình điều khiển, tính năng ít dùng hoặc cơ chế sinh mã có thể khiến lớp mới xuất hiện trong lúc ứng dụng phục vụ yêu cầu.

Khi quan sát JVM, cần trả lời ba câu hỏi khác nhau:

1. Hiện JVM đang giữ bao nhiêu lớp đã nạp?
2. Từ khi JVM khởi động, đã có bao nhiêu lượt lớp được nạp?
3. Từ khi JVM khởi động, đã có bao nhiêu lớp được dỡ?

`ClassLoadingMXBean` cung cấp ba số liệu tổng hợp này. Nó giúp nhận ra quá trình khởi động chưa ổn định, tốc độ nạp lớp thay đổi hoặc xu hướng giữ lại lớp cần điều tra. Nó không tự xác định tên lớp gây tăng bộ nhớ hoặc chỉ ra nguyên nhân rò rỉ.

Lấy bean của JVM hiện tại:

```java
// Đoạn mã minh họa; cần import từ java.lang.management.
ClassLoadingMXBean bean = ManagementFactory.getClassLoadingMXBean();
```

Mỗi JVM có một bean loại này; tên JMX là `java.lang:type=ClassLoading`. Xem [ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html).

## 2. Phân biệt số hiện tại và bộ đếm tích lũy

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getLoadedClassCount()` | `int` | Số lớp hiện đang được nạp trong JVM |
| `getTotalLoadedClassCount()` | `long` | Tổng số lớp đã được nạp từ khi JVM bắt đầu chạy |
| `getUnloadedClassCount()` | `long` | Tổng số lớp đã được dỡ từ khi JVM bắt đầu chạy |

Các ý nghĩa và kiểu trả về này thuộc hợp đồng của [ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html).

Số hiện tại có thể tăng hoặc giảm. Hai số tổng là bộ đếm tích lũy trong một vòng đời JVM. Khi tiến trình khởi động lại, không nối các bộ đếm mới vào mẫu nền của JVM cũ.

Ví dụ giả định tại một thời điểm yên:

```text
Tổng từng nạp:  1200
Tổng đã dỡ:     200
Hiện đang nạp: 1000
```

Cách hiểu là JVM đã trải qua nhiều hoạt động nạp hơn số lớp còn được giữ tại thời điểm đó. Không diễn giải `totalLoaded=1200` thành “đang có 1200 lớp”.

Về mặt mô hình, số đang nạp tương ứng số từng nạp trừ số đã dỡ. Tuy nhiên, ba lệnh gọi phương thức là ba lần đọc nối tiếp, không phải một ảnh chụp nguyên tử. JVM có thể nạp/dỡ lớp giữa chúng. Vì thế, trong giám sát thực tế, đọc trực tiếp số hiện tại và không yêu cầu đẳng thức chính xác giữa ba giá trị lấy ở ba thời điểm.

Không dùng `getLoadedClassCount()` như một bộ đếm chỉ tăng. Số này giảm có thể phản ánh việc dỡ lớp hợp lệ, không nhất thiết là lỗi dữ liệu.

## 3. “Một lớp” không phải “một đối tượng” hay “một tệp nguồn”

Tạo một triệu đối tượng từ cùng một lớp không có nghĩa nạp thêm một triệu lớp. Số đối tượng và số lớp là hai đại lượng khác nhau.

Tương tự, số lớp JVM đã nạp không bằng số tệp `.java`, số tệp `.class` trong kho mã hoặc số JAR. Một tệp nguồn có thể khai báo nhiều lớp; JVM còn nạp lớp từ thư viện và có thể sử dụng các lớp được sinh khi chạy.

Ở mức JVM, với lớp thông thường, danh tính lớp phụ thuộc cả tên nhị phân lẫn class loader định nghĩa lớp. Hai class loader định nghĩa cùng tên không mặc nhiên tạo cùng một kiểu. Quy tắc này nằm trong [JVM Specification, phần tạo và nạp lớp](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3).

Vì vậy, một hệ thống plugin có thể làm số lớp tăng dù danh sách tên nghiệp vụ trông gần như không đổi. Ngược lại, chỉ đếm tên duy nhất trong một danh sách tự thu thập không thay thế được số liệu JVM.

Số lớp cũng không phải số byte bộ nhớ. Kích thước dữ liệu mô tả lớp khác nhau; bộ nhớ JVM còn phục vụ nhiều mục đích khác. Không lấy “số lớp nhân một hằng số” để coi như lượng bộ nhớ chính xác.

## 4. Ví dụ chạy được: số liệu thật và kiểm tra phép tính

Chương trình sau có hai chế độ:

- Mặc định: dùng dữ liệu cố định để minh họa số hiện tại và số tăng giữa hai mẫu.
- `--live`: đọc JVM thật, nạp một lớp theo tên rồi yêu cầu khởi tạo lớp đó.

Lưu thành **ClassLoadingDemo.java**, dùng Java 17 trở lên:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.util.Locale;

public class ClassLoadingDemo {
    private static boolean payloadInitialized;

    record Sample(long total, long unloaded, int current) {}

    static class Payload {
        static {
            payloadInitialized = true;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        if (args.length == 0) {
            Sample before = new Sample(1000L, 100L, 900);
            Sample after = new Sample(1120L, 120L, 1000);
            print("before", before);
            print("after", after);
            changes(before, after);
            return;
        }

        if (args.length != 1 || !"--live".equals(args[0])) {
            throw new IllegalArgumentException("Use no arguments or --live");
        }

        ClassLoadingMXBean bean = ManagementFactory.getClassLoadingMXBean();
        read(bean); // Warm up the sampling helper itself.
        Sample before = read(bean);

        ClassLoader loader = ClassLoadingDemo.class.getClassLoader();
        String name = "ClassLoadingDemo$Payload";
        Class<?> loaded = Class.forName(name, false, loader);
        boolean initializedAfterLoad = payloadInitialized;
        Sample afterLoad = read(bean);

        Class.forName(name, true, loader);
        boolean initializedAfterRequest = payloadInitialized;
        Sample afterInitialization = read(bean);

        print("before", before);
        print("after-load", afterLoad);
        print("after-initialization", afterInitialization);
        changes(before, afterLoad);
        System.out.println("loaded-name=" + loaded.getName());
        System.out.println("initialized-after-load=" + initializedAfterLoad);
        System.out.println("initialized-after-request=" + initializedAfterRequest);
    }

    private static Sample read(ClassLoadingMXBean bean) {
        long total = bean.getTotalLoadedClassCount();
        long unloaded = bean.getUnloadedClassCount();
        int current = bean.getLoadedClassCount();
        return new Sample(total, unloaded, current);
    }

    private static void print(String label, Sample sample) {
        System.out.printf(Locale.ROOT,
                "%s total=%d unloaded=%d current=%d%n",
                label, sample.total(), sample.unloaded(), sample.current());
    }

    private static void changes(Sample before, Sample after) {
        if (after.total() < before.total()
                || after.unloaded() < before.unloaded()) {
            System.out.println("baseline-invalid");
            return;
        }

        long newlyLoaded = after.total() - before.total();
        long newlyUnloaded = after.unloaded() - before.unloaded();
        long currentChange = (long) after.current() - before.current();
        System.out.printf(Locale.ROOT,
                "newly-loaded=%d newly-unloaded=%d current-change=%d%n",
                newlyLoaded, newlyUnloaded, currentChange);
    }
}
```

Biên dịch và chạy dữ liệu cố định:

```shell
javac ClassLoadingDemo.java
java ClassLoadingDemo
```

Stdout chính xác:

```text
before total=1000 unloaded=100 current=900
after total=1120 unloaded=120 current=1000
newly-loaded=120 newly-unloaded=20 current-change=100
```

Các số mặc định do chương trình tự tạo để minh họa. Chúng không phải số lớp tối thiểu hay thông thường của một JVM.

Chạy với JVM thật:

```shell
java ClassLoadingDemo --live
```

Các dòng số lượng lớp thay đổi theo bản JDK, môi trường và hoạt động trong lúc lấy mẫu. Với cách chạy bình thường của ví dụ, ba dòng cuối là:

```text
loaded-name=ClassLoadingDemo$Payload
initialized-after-load=false
initialized-after-request=true
```

Đừng kiểm thử chế độ thật bằng yêu cầu `newly-loaded=1`. Ngoài lớp mục tiêu, JVM có thể nạp lớp hỗ trợ; bản thân mã đo và thư viện dùng trong ví dụ cũng có thể gây nạp lớp. Lần gọi `read(bean)` để làm nóng chỉ giảm một nguồn nhiễu, không cô lập toàn bộ JVM.

## 5. Nạp lớp khác khởi tạo lớp

Trong ví dụ:

```java
Class.forName(name, false, loader);
```

Yêu cầu tìm/nạp lớp nhưng không yêu cầu khởi tạo nó. Đổi tham số thành `true` yêu cầu khởi tạo lớp nếu chưa khởi tạo. Bộ khởi tạo `static` của `Payload` đặt cờ để ta quan sát sự khác biệt.

Hợp đồng của [Class.forName(String, boolean, ClassLoader)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)) mô tả tham số này.

`ClassLoadingMXBean` không có bộ đếm “số lớp đã chạy bộ khởi tạo static”. Vì vậy, sự tăng số lớp được nạp không chứng minh rằng tất cả chúng đã khởi tạo, và việc một lớp khởi tạo không nhất thiết làm số lớp tăng thêm đúng một.

Các bước nạp, liên kết và khởi tạo được phân biệt trong [Java Language Specification, chương 12](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html). Khi chẩn đoán lỗi hoặc thời gian khởi động, đừng gộp chúng thành một hành động duy nhất chỉ vì có chung liên quan đến lớp.

## 6. Dỡ lớp không xảy ra ngay khi đối tượng cuối cùng biến mất

Với các lớp thông thường do một class loader định nghĩa, khả năng dỡ lớp gắn với việc class loader định nghĩa chúng có thể được GC thu hồi. Chỉ bỏ một biến tham chiếu đến đối tượng nghiệp vụ không bảo đảm lớp và class loader sẽ biến mất.

[JLS 12.7](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7) nêu điều kiện dỡ lớp và tính tùy chọn của tối ưu hóa này. Không xây chức năng ứng dụng phụ thuộc việc một lớp chắc chắn bị dỡ vào một thời điểm cụ thể.

Một tình huống cần điều tra trong hệ thống plugin:

```text
Nạp plugin bằng class loader riêng
    -> plugin chạy
    -> plugin ngừng
    -> vẫn còn tham chiếu giữ class loader cũ
    -> các lớp của plugin cũ chưa thể được thu hồi theo vòng đời mong muốn
```

Ví dụ nguồn tham chiếu cần xem xét là luồng nền chưa dừng, callback/listener chưa gỡ hoặc bộ đệm thuộc thành phần sống lâu hơn plugin. Đây là hướng tìm kiếm theo cấu trúc ứng dụng, không phải thông tin mà ba bộ đếm tự chỉ ra.

`unloaded=0` không đủ để kết luận rò rỉ. Nhiều ứng dụng sử dụng một tập lớp ổn định trong suốt vòng đời; không có lý do phải dỡ chúng sau mỗi yêu cầu.

Cũng không gọi GC liên tục để “ép” số unloaded tăng và dùng đó làm tiêu chí chương trình đúng. Tối ưu hóa dỡ lớp và thời điểm thu gom không phải giao thức xác nhận nghiệp vụ.

## 7. Đọc xu hướng trong giám sát

Một cách tổ chức quan sát là lưu số hiện tại cùng hai bộ đếm tích lũy, có thời gian và định danh vòng đời JVM. Muốn tính tốc độ nạp theo giây, lấy hiệu total trong cùng vòng đời chia cho thời gian quan sát thực tế.

| Quan sát | Giả thuyết nên kiểm tra |
| --- | --- |
| Current và total tăng mạnh lúc khởi động rồi ổn định | Ứng dụng có thể đang hoàn thành việc nạp thư viện và tính năng ban đầu |
| Total và unloaded cùng tăng, current gần ổn định | Có luân chuyển lớp; xem các hoạt động sinh mã hoặc vòng đời plugin |
| Current tiếp tục tăng sau những lần tải lại tính năng | Kiểm tra các class loader cũ có bị giữ không |
| Số lớp ổn định nhưng bộ nhớ tăng | Cần nguồn đo khác; không thể loại trừ vấn đề bộ nhớ chỉ bằng số lớp |

Các cách diễn giải này là giả thuyết, không phải kết luận tự động. Đối chiếu với tải, thay đổi cấu hình, số liệu bộ nhớ và sự kiện nạp/dỡ lớp.

Không đặt một ngưỡng “vượt N lớp là lỗi” cho mọi ứng dụng. Quy mô framework và số tính năng tạo mức nền rất khác nhau. So sánh cùng ứng dụng dưới tải và giai đoạn vận hành tương đương thường có giá trị hơn một con số tuyệt đối.

## 8. Khi cần biết lớp nào được nạp

`ClassLoadingMXBean` không liệt kê tên từng lớp. Để điều tra sự kiện trên HotSpot hiện đại, có thể khởi động ứng dụng với nhật ký thống nhất:

```shell
java "-Xlog:class+load=info,class+unload=info" ClassLoadingDemo --live
```

Lệnh này bổ sung nhật ký nạp/dỡ lớp vào đầu ra; stdout mẫu ở trên chỉ áp dụng khi không bật thêm nhật ký. Danh sách tùy chọn được mô tả trong [tài liệu lệnh java](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).

Chọn phạm vi và khoảng thời gian ghi phù hợp vì nhật ký chi tiết có thể tạo nhiều dữ liệu. Với JVM đang chạy, công cụ `jcmd` có thể hỗ trợ điều tra class loader; xem danh sách lệnh thực sự được JVM đích hỗ trợ bằng `jcmd <pid> help`, theo [tài liệu jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html).

`isVerbose()` và `setVerbose(boolean)` cũng có trên bean. `setVerbose` thay đổi đầu ra chẩn đoán của hệ thống nạp lớp trên toàn JVM, không phải chỉ bật thêm thông tin cho một lần đọc của người gọi. Vì thế, mã thu thập số liệu thông thường chỉ cần đọc bộ đếm; việc bật nhật ký chi tiết là quyết định vận hành riêng.

## 9. Tự kiểm tra

1. Tạo thêm 10.000 đối tượng cùng một lớp có nghĩa totalLoaded tăng 10.000 không? **Không.**
2. Total tăng 120, unloaded tăng 20 thì trong ví dụ dữ liệu ổn định current thay đổi bao nhiêu? **Tăng 100.**
3. Có nên dùng hiệu current làm số lớp mới nạp không? **Không**, vì current còn chịu ảnh hưởng của việc dỡ lớp.
4. Dữ liệu total giảm sau khi nối lại giám sát cần xử lý thế nào? **Xác minh vòng đời JVM và lấy lại mẫu nền**, không biến hiệu âm thành số lớp âm hợp lệ.
5. Class.forName với initialize=false có chứng minh bộ khởi tạo static đã chạy không? **Không.**
6. Current liên tục tăng có đủ để khẳng định rò rỉ class loader không? **Chưa đủ**; cần xác định lớp, class loader và đường tham chiếu giữ chúng.

Sau bài này, người học cần phân biệt đúng số hiện tại với số tích lũy, quan sát lớp mà không đồng nhất với đối tượng hoặc byte bộ nhớ, và biết chuyển sang nguồn sự kiện khi cần tìm tên lớp hay nguyên nhân.
