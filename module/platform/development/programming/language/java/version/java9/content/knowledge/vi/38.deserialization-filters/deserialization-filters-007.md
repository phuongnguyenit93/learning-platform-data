# Mẫu lọc tên lớp, package, mô-đun và giới hạn tài nguyên khi giải tuần tự Java

## Mục tiêu

Trong nhánh **Lọc giải tuần tự**, Java 9 giới thiệu **Serialization Filtering** thông qua **ObjectInputFilter** để kiểm tra dữ liệu trong quá trình giải tuần tự. Bộ lọc có thể quyết định lớp nào được phép, lớp nào bị từ chối và giới hạn độ phức tạp của object graph.

Bài này tập trung vào cú pháp pattern cho tên lớp, package, mô-đun và bốn giới hạn tài nguyên: **maxdepth**, **maxrefs**, **maxbytes**, **maxarray**. Trọng tâm là viết allow-list có thứ tự đúng, hiểu kết quả **ALLOWED / REJECTED / UNDECIDED**, áp dụng filter cho từng stream hoặc toàn JVM và tránh nhầm pattern filter với một cơ chế bảo vệ toàn diện.

## 1. ObjectInputFilter hoạt động ở đâu?

Khi đọc đối tượng bằng **ObjectInputStream**, dữ liệu serialized được giải mã thành object graph. Nếu nguồn dữ liệu không đáng tin cậy, graph có thể chứa lớp không mong muốn, mảng quá lớn hoặc cấu trúc lồng nhau quá sâu.

**ObjectInputFilter** cho phép kiểm tra thông tin trong quá trình này. Filter có thể được gọi khi runtime xử lý lớp, mảng hoặc các chỉ số về graph. Thông tin được cung cấp qua **ObjectInputFilter.FilterInfo**:

| Phương thức | Ý nghĩa |
|---|---|
| **serialClass()** | Lớp đang được kiểm tra; có thể là **null** ở lần kiểm tra chỉ cung cấp chỉ số graph |
| **arrayLength()** | Độ dài mảng; **-1** nếu lần kiểm tra hiện tại không phải mảng |
| **depth()** | Độ sâu hiện tại của object graph |
| **references()** | Số reference đã được tính trong graph |
| **streamBytes()** | Số byte đã được đọc từ stream |

Filter trả về một trong ba trạng thái:

- **ALLOWED**: filter cho phép đối tượng hoặc trạng thái đang kiểm tra.
- **REJECTED**: từ chối; ObjectInputStream dừng giải tuần tự và ném **InvalidClassException**.
- **UNDECIDED**: filter không đưa ra quyết định cho lần kiểm tra đó. Đây không phải một lệnh từ chối.

Pattern filter không tự động bật chỉ vì ứng dụng dùng ObjectInputStream. Cần cấu hình filter qua system property, security property, API toàn JVM hoặc API cho từng stream.

## 2. Cấu trúc chuỗi pattern

Pattern filter là một chuỗi gồm nhiều phần, phân tách bằng dấu chấm phẩy. Một phần có thể là pattern tên lớp, package, mô-đun hoặc giới hạn tài nguyên.

Ví dụ:

```text
maxdepth=20;maxrefs=500;maxbytes=100000;maxarray=1000;example.dto.**;java.base/java.util.*;!*
```

Các quy tắc cú pháp cần nhớ:

1. Dùng dấu chấm phẩy để phân tách từng pattern.
2. Khoảng trắng là một phần của pattern và có ý nghĩa. Tránh chèn khoảng trắng thừa quanh tên lớp hoặc dấu bằng.
3. Các giới hạn được kiểm tra trước quy tắc tên lớp, bất kể vị trí của chúng trong chuỗi. Đặt giới hạn ở đầu chuỗi giúp người đọc nhận ra thứ tự này.
4. Các pattern lớp được xét từ trái sang phải; **pattern lớp đầu tiên khớp** sẽ quyết định **ALLOWED** hoặc **REJECTED**.
5. Nếu một giới hạn xuất hiện nhiều lần, giá trị cuối cùng được dùng.
6. Giá trị giới hạn phải là số nguyên không âm có thể phân tích thành **long**. Tên giới hạn không hợp lệ, giá trị âm hoặc pattern sai cú pháp khiến **createFilter()** ném **IllegalArgumentException**.

Không nên coi chuỗi pattern như một biểu thức chính quy. Đây là cú pháp riêng với quy tắc wildcard và thứ tự khớp được xác định.

## 3. Pattern cho tên lớp và package

Tên lớp được so khớp theo tên mà **Class.getName()** trả về.

| Pattern | Phạm vi khớp |
|---|---|
| `com.example.dto.Record` | Chỉ lớp có tên chính xác này |
| `com.example.dto.*` | Các lớp trực tiếp trong package `com.example.dto` |
| `com.example.dto.**` | Các lớp trong package `com.example.dto` và mọi subpackage |
| `text*` | Tên lớp bắt đầu bằng tiền tố `text` |
| `*` | Mọi tên lớp |

Sự khác biệt giữa `.*` và `.**` rất quan trọng:

- `com.example.dto.*` khớp `com.example.dto.Record`.
- `com.example.dto.*` không khớp `com.example.dto.internal.Record`.
- `com.example.dto.**` khớp cả hai lớp trên.

Wildcard `*` ở cuối pattern cũng có thể dùng cho tiền tố tên lớp, ví dụ `com.example.dto.Dto*`. Pattern này dựa trên tên lớp, không phải tên file hoặc đường dẫn package tùy ý.

### Dấu ! để từ chối

Đặt dấu `!` ở đầu pattern để từ chối lớp khớp với phần còn lại:

```text
!com.example.dto.internal.**
```

Pattern trên từ chối các lớp thuộc package `com.example.dto.internal` và các subpackage của nó.

### Thứ tự pattern quyết định kết quả

Pattern lớp đầu tiên khớp sẽ thắng. Vì vậy, đặt ngoại lệ từ chối trước pattern cho phép rộng:

```text
!com.example.dto.internal.**;com.example.dto.**;!*
```

Kết quả:

- Lớp trong `com.example.dto.internal` bị từ chối.
- Lớp khác trong `com.example.dto` được cho phép.
- Lớp không khớp các pattern trước bị từ chối bởi `!*`.

Nếu đảo thứ tự thành `com.example.dto.**;!com.example.dto.internal.**;!*`, pattern cho phép rộng sẽ khớp trước. Ngoại lệ từ chối phía sau không còn cơ hội được xét.

## 4. Pattern theo mô-đun

Có thể giới hạn pattern theo tên mô-đun bằng cú pháp:

```text
module-name/class-pattern
```

Phần trước dấu gạch chéo là tên mô-đun; phần sau là pattern tên lớp. Mô-đun phải khớp với **Class.getModule().getName()** của lớp, sau đó phần tên lớp mới được so khớp.

Ví dụ:

| Pattern | Ý nghĩa |
|---|---|
| `java.base/java.util.ArrayList` | Chỉ `ArrayList` trong mô-đun `java.base` |
| `java.base/java.util.*` | Các lớp trực tiếp trong package `java.util` thuộc `java.base` |
| `java.base/java.util.**` | Package `java.util` và các subpackage trong `java.base` |
| `java.base/*` | Mọi lớp thuộc mô-đun `java.base` |

Không có dấu gạch chéo thì tên mô-đun không được so sánh. Pattern `java.util.*` vì thế chỉ xét tên package/lớp, bất kể mô-đun chứa lớp.

Tên mô-đun không phải tên package. Ví dụ, `java.base` là tên mô-đun nền tảng; `java.util` là package. Pattern `java.base/java.util.*` kết hợp cả hai điều kiện.

Nếu pattern có dấu gạch chéo nhưng thiếu tên mô-đun hoặc thiếu phần tên lớp phía sau, pattern không hợp lệ. Lớp trong unnamed module không có tên mô-đun để khớp với một module prefix cụ thể.

## 5. Mảng được so khớp theo kiểu phần tử

Khi **serialClass()** là kiểu mảng, pattern tên lớp được so khớp theo **kiểu phần tử**, không theo tên kiểu mảng. Mảng nhiều chiều cũng được xử lý theo kiểu phần tử cuối cùng.

Ví dụ:

- `com.example.dto.Record[]` được xét theo lớp `com.example.dto.Record`.
- `com.example.dto.Record[][]` cũng được xét theo lớp `com.example.dto.Record`.
- Pattern `com.example.dto.**` có thể khớp các mảng chứa kiểu phần tử thuộc package đó.

Độ dài mảng được kiểm soát riêng bằng **maxarray**. Pattern tên lớp và giới hạn độ dài mảng giải quyết hai câu hỏi khác nhau: kiểu phần tử có được phép không, và mảng có quá lớn không.

## 6. Bốn giới hạn tài nguyên

Các giới hạn là pattern dạng `name=value`. Giá trị là số nguyên không âm.

| Giới hạn | Ý nghĩa |
|---|---|
| `maxdepth=20` | Độ sâu tối đa của object graph |
| `maxrefs=500` | Số reference tối đa được tính trong graph |
| `maxbytes=100000` | Số byte tối đa đã đọc từ stream |
| `maxarray=1000` | Độ dài tối đa của một mảng |

Ví dụ kết hợp:

```text
maxdepth=20;maxrefs=500;maxbytes=100000;maxarray=1000
```

Nếu bất kỳ giới hạn nào bị vượt, pattern filter trả về **REJECTED**. Các giới hạn được kiểm tra trước pattern lớp, nên lớp nằm trong allow-list vẫn bị từ chối khi graph vượt ngưỡng.

### Ý nghĩa và giới hạn của từng ngưỡng

**maxdepth** giúp hạn chế graph lồng nhau quá sâu. Nó hữu ích khi dữ liệu có thể tạo cấu trúc đệ quy hoặc chuỗi tham chiếu dài.

**maxrefs** giới hạn số reference trong graph. Nó giúp kiểm soát graph có quá nhiều liên kết hoặc quá nhiều đối tượng được tham chiếu, kể cả khi độ sâu không lớn.

**maxbytes** giới hạn lượng byte được đọc từ stream. Nó giúp tránh xử lý một luồng serialized quá lớn.

**maxarray** giới hạn chiều dài từng mảng. Nó không phải tổng dung lượng của mọi mảng cộng lại; nhiều mảng nhỏ vẫn có thể có tổng kích thước đáng kể.

Các giá trị ví dụ chỉ là ngưỡng minh họa. Hãy đo kích thước graph bình thường của ứng dụng và chọn giới hạn có khoảng an toàn phù hợp. Ngưỡng quá thấp có thể từ chối dữ liệu hợp lệ; ngưỡng quá cao giảm tác dụng bảo vệ.

## 7. Kết hợp allow-list, deny-list và catch-all

Với dữ liệu đầu vào không đáng tin cậy, nên ưu tiên **allow-list**: chỉ liệt kê những lớp mà use case thực sự cần.

Ví dụ:

```text
maxdepth=20;maxrefs=500;maxbytes=100000;maxarray=1000;!com.example.dto.internal.**;com.example.dto.**;java.base/java.lang.*;java.base/java.util.*;!*
```

Ý nghĩa:

1. Giới hạn độ sâu, số reference, số byte và độ dài mảng.
2. Từ chối package nội bộ nhạy cảm trước khi cho phép package DTO rộng hơn.
3. Cho phép các lớp DTO và một số lớp nền tảng cần cho graph.
4. Từ chối mọi lớp không khớp bằng `!*`.

`!*` là điểm quan trọng của allow-list nghiêm ngặt. Nếu bỏ pattern này, lớp không khớp các pattern khác thường nhận trạng thái **UNDECIDED**, nghĩa là filter không đưa ra quyết định từ chối.

Không nên dùng một allow-list mẫu mà không kiểm tra graph thật. Một DTO có thể chứa String, wrapper, collection hoặc kiểu hỗ trợ khác; từng kiểu cần thiết phải được cân nhắc rõ ràng.

### Khi nào dùng deny-list?

Deny-list hữu ích để chặn một lớp hoặc package đã được xác định là không nên xuất hiện. Tuy nhiên, deny-list đơn thuần không bảo đảm an toàn: pattern khớp tên lớp cụ thể, không tự áp dụng cho mọi lớp con hoặc mọi kiểu triển khai interface của lớp đó.

Nếu có thể, hãy xác định tập lớp hợp lệ của từng điểm nhận dữ liệu và dùng allow-list. Deny-list nên là lớp bảo vệ bổ sung cho các trường hợp đã biết.

## 8. Cấu hình filter cho một stream

Dùng **ObjectInputFilter.Config.createFilter(String)** để tạo filter từ pattern. Sau đó gắn filter vào ObjectInputStream trước khi đọc đối tượng:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=500;maxbytes=100000;maxarray=1000;"
        + "!com.example.dto.internal.**;"
        + "com.example.dto.**;"
        + "java.base/java.lang.*;"
        + "java.base/java.util.*;"
        + "!*");

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
    return value;
}
```

Filter gắn với stream đó. Đây là lựa chọn phù hợp khi mỗi điểm nhận dữ liệu có tập lớp và giới hạn tài nguyên riêng.

### Cấu hình toàn JVM

Có thể đặt filter toàn JVM bằng system property:

```bash
java -Djdk.serialFilter="maxdepth=20;maxrefs=500;maxbytes=100000;maxarray=1000;com.example.dto.**;!*" com.example.Main
```

Hoặc cấu hình qua **ObjectInputFilter.Config.setSerialFilter(filter)** trước khi ứng dụng tạo ObjectInputStream. Filter toàn JVM ảnh hưởng đến các luồng giải tuần tự trong tiến trình; cần kiểm kê các use case để tránh một policy chung quá chặt hoặc quá rộng.

**jdk.serialFilter** cũng có thể được cấu hình như Security Property trong file cấu hình bảo mật của runtime. System Property có thể ghi đè giá trị Security Property.

Không nên đợi tới lúc ứng dụng đã tạo các ObjectInputStream rồi mới cài đặt filter toàn JVM. Hãy cấu hình ở giai đoạn khởi động.

## 9. Filter factory và filter theo ngữ cảnh từ Java 17

Từ Java 17, **JEP 415** bổ sung filter factory để chọn hoặc kết hợp filter theo ngữ cảnh cho từng hoạt động giải tuần tự.

Điều này hữu ích khi một tiến trình có nhiều thành phần nhận dữ liệu với các yêu cầu khác nhau. Ví dụ, một endpoint chỉ nhận DTO đơn giản, còn một thành phần nội bộ cần collection và kiểu dữ liệu phong phú hơn.

Filter factory có thể xem thông tin ngữ cảnh sẵn có của ứng dụng, sau đó chọn filter phù hợp cho ObjectInputStream. Factory được cấu hình qua **ObjectInputFilter.Config.setSerialFilterFactory()** hoặc property tương ứng.

Cần phân biệt:

- **Java 9 / JEP 290** cung cấp ObjectInputFilter, pattern filter và filter gắn với ObjectInputStream hoặc toàn JVM.
- **Java 17 / JEP 415** bổ sung cơ chế filter factory để chọn filter theo từng ngữ cảnh.

Filter factory không làm pattern trở nên tự động an toàn. Policy của từng ngữ cảnh vẫn phải xác định allow-list và resource limit phù hợp.

## 10. Filter tùy chỉnh và trạng thái UNDECIDED

Pattern filter phù hợp với quy tắc theo tên lớp và giới hạn số liệu. Nếu cần kiểm tra logic phức tạp hơn, có thể triển khai **ObjectInputFilter** và đọc **FilterInfo**.

Ví dụ khung kiểm tra:

```java
ObjectInputFilter filter = info -> {
    if (info.depth() > 20
            || info.references() > 500
            || info.streamBytes() > 100_000
            || info.arrayLength() > 1_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == TransferRecord.class
            || type == String.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

Đây là khung minh họa; ứng dụng phải thay **TransferRecord** bằng kiểu thực tế và xử lý thêm các kiểu cần thiết trong graph.

**serialClass()** có thể là **null**, vì một số lần gọi filter chỉ cung cấp thông tin về độ sâu, reference hoặc số byte. **arrayLength()** bằng **-1** khi không kiểm tra mảng. Vì vậy, không được gọi phương thức trên serialClass trước khi kiểm tra null.

Khi filter không đủ thông tin để quyết định, **UNDECIDED** có nghĩa là nhường quyết định cho cơ chế filter khác hoặc bước xử lý tiếp theo. Nếu mục tiêu là allow-list nghiêm ngặt, lớp không được liệt kê phải bị từ chối thay vì để UNDECIDED.

## 11. Ví dụ Java hoàn chỉnh: kiểm tra pattern và giới hạn

Chương trình sau kiểm tra package, module, wildcard, thứ tự pattern và bốn giới hạn. Nó tạo **FilterInfo** mẫu để kiểm tra trực tiếp kết quả của pattern filter, không đọc dữ liệu serialized từ bên ngoài.

Tạo tệp **FilterPatternDemo.java**:

```java
package example.dto;

import java.io.File;
import java.io.ObjectInputFilter;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.concurrent.ConcurrentHashMap;

public class FilterPatternDemo {
    public static final class AllowedRecord implements Serializable {
        private static final long serialVersionUID = 1L;
        private final String value;

        public AllowedRecord(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    private record Snapshot(
            Class<?> serialClass,
            long arrayLength,
            long depth,
            long references,
            long streamBytes) implements ObjectInputFilter.FilterInfo {}

    private static final String PATTERN =
            "maxdepth=20;maxrefs=500;maxbytes=100000;maxarray=1000;"
            + "!java.base/java.io.**;example.dto.**;"
            + "java.base/java.util.*;!*";

    private static ObjectInputFilter.Status check(
            ObjectInputFilter filter,
            Class<?> type,
            long arrayLength,
            long depth,
            long references,
            long streamBytes) {
        return filter.checkInput(
                new Snapshot(type, arrayLength, depth, references, streamBytes));
    }

    private static void expect(
            String label,
            ObjectInputFilter.Status actual,
            ObjectInputFilter.Status expected) {
        if (actual != expected) {
            throw new AssertionError(
                    label + ": expected " + expected + " but got " + actual);
        }
        System.out.println(label + ": " + actual);
    }

    public static void main(String[] args) {
        ObjectInputFilter filter =
                ObjectInputFilter.Config.createFilter(PATTERN);

        expect("DTO package",
                check(filter, AllowedRecord.class, -1, 1, 1, 128),
                ObjectInputFilter.Status.ALLOWED);
        expect("java.util package in java.base",
                check(filter, ArrayList.class, -1, 1, 2, 256),
                ObjectInputFilter.Status.ALLOWED);
        expect("java.util subpackage",
                check(filter, ConcurrentHashMap.class, -1, 1, 2, 256),
                ObjectInputFilter.Status.REJECTED);
        expect("explicit java.io rejection",
                check(filter, File.class, -1, 1, 2, 256),
                ObjectInputFilter.Status.REJECTED);
        expect("unlisted class",
                check(filter, String.class, -1, 1, 2, 256),
                ObjectInputFilter.Status.REJECTED);
        expect("array class uses element type",
                check(filter, ArrayList[].class, 5, 1, 3, 512),
                ObjectInputFilter.Status.ALLOWED);

        ObjectInputFilter allowFirst = ObjectInputFilter.Config.createFilter(
                "example.dto.**;!example.dto.**;!*");
        expect("first matching allow wins",
                check(allowFirst, AllowedRecord.class, -1, 1, 1, 128),
                ObjectInputFilter.Status.ALLOWED);

        ObjectInputFilter rejectFirst = ObjectInputFilter.Config.createFilter(
                "!example.dto.**;example.dto.**;!*");
        expect("first matching reject wins",
                check(rejectFirst, AllowedRecord.class, -1, 1, 1, 128),
                ObjectInputFilter.Status.REJECTED);

        ObjectInputFilter noCatchAll = ObjectInputFilter.Config.createFilter(
                "example.dto.**");
        expect("unmatched without catch-all",
                check(noCatchAll, String.class, -1, 1, 1, 128),
                ObjectInputFilter.Status.UNDECIDED);

        ObjectInputFilter limits = ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=500;maxbytes=100000;maxarray=1000;*");
        expect("depth limit",
                check(limits, AllowedRecord.class, -1, 21, 1, 128),
                ObjectInputFilter.Status.REJECTED);
        expect("reference limit",
                check(limits, AllowedRecord.class, -1, 1, 501, 128),
                ObjectInputFilter.Status.REJECTED);
        expect("stream byte limit",
                check(limits, AllowedRecord.class, -1, 1, 1, 100001),
                ObjectInputFilter.Status.REJECTED);
        expect("array length limit",
                check(limits, int[].class, 1001, 1, 1, 128),
                ObjectInputFilter.Status.REJECTED);
        expect("null class still checks limits",
                check(limits, null, -1, 1, 1, 100001),
                ObjectInputFilter.Status.REJECTED);
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac --release 17 -Xlint:all -d out FilterPatternDemo.java
java -cp out example.dto.FilterPatternDemo
```

Stdout chính xác:

```text
DTO package: ALLOWED
java.util package in java.base: ALLOWED
java.util subpackage: REJECTED
explicit java.io rejection: REJECTED
unlisted class: REJECTED
array class uses element type: ALLOWED
first matching allow wins: ALLOWED
first matching reject wins: REJECTED
unmatched without catch-all: UNDECIDED
depth limit: REJECTED
reference limit: REJECTED
stream byte limit: REJECTED
array length limit: REJECTED
null class still checks limits: REJECTED
```

Ví dụ xác nhận các pattern được áp dụng theo đúng thứ tự. **java.util.*** cho phép lớp trong package **java.util** nhưng không cho phép lớp thuộc **java.util.concurrent**; **!* ** từ chối lớp không nằm trong allow-list. Các kiểm tra tài nguyên được thực hiện ngay cả khi serialClass là null.

## 12. Giới hạn bảo vệ và lỗi thường gặp

Serialization filtering là một lớp phòng vệ quan trọng, nhưng không thay thế xác thực dữ liệu, kiểm tra nghiệp vụ hoặc thiết kế giao thức an toàn.

Các giới hạn cần hiểu:

- Pattern lớp so khớp tên lớp, không kiểm tra supertype hoặc interface mà lớp triển khai.
- Từ chối một lớp không tự động từ chối mọi subclass của lớp đó.
- Pattern filter không có trạng thái để quyết định dựa trên các object đã đọc trước đó.
- Pattern filter không thể đặt giới hạn array khác nhau tùy tên lớp; **maxarray** áp dụng như một ngưỡng chung.
- Filter không kiểm tra giá trị trường hoặc tính hợp lệ nghiệp vụ của object.
- Lớp được allow vẫn có thể chứa logic giải tuần tự riêng; cho phép lớp không đồng nghĩa dữ liệu của nó đã được xác thực.

Lỗi thường gặp:

1. **Chỉ dùng deny-list**: có thể bỏ sót lớp nguy hiểm chưa được liệt kê. Ưu tiên allow-list theo từng use case.
2. **Đặt !* trước allow-list**: pattern đầu tiên khớp sẽ thắng, nên mọi lớp bị từ chối trước khi tới rule cho phép.
3. **Đặt deny exception sau package allow rộng**: lớp đã khớp rule allow sẽ không đi tiếp đến rule deny phía sau.
4. **Nhầm .* với .****: một pattern chỉ khớp package trực tiếp, pattern kia bao gồm subpackage.
5. **Nhầm package với module**: dùng module/package-pattern khi muốn giới hạn cả hai.
6. **Quên !* trong allow-list nghiêm ngặt**: lớp không khớp có thể trả UNDECIDED, không phải REJECTED.
7. **Cho rằng giới hạn chỉ áp dụng cho lớp bị từ chối**: resource limit được kiểm tra trước pattern lớp và có thể từ chối cả lớp nằm trong allow-list.
8. **Bỏ qua arrayLength**: một graph ít lớp nhưng có mảng khổng lồ vẫn có thể tiêu thụ nhiều bộ nhớ.
9. **Coi ALLOWED là xác nhận toàn bộ object hợp lệ**: filter chỉ quyết định theo policy của nó; ứng dụng vẫn phải kiểm tra dữ liệu và quy tắc nghiệp vụ.
10. **Giả định filter đã bật mặc định**: phải cấu hình filter rõ ràng ở JVM hoặc ObjectInputStream.

Với dữ liệu đến từ nguồn không đáng tin cậy, chỉ giải tuần tự khi thật sự cần tương thích với Java Serialization. Hãy dùng allow-list hẹp, đặt resource limit theo graph hợp lệ và cân nhắc định dạng trao đổi dữ liệu ít rủi ro hơn cho API mới.

## Kết luận

Pattern filter của ObjectInputFilter cho phép kết hợp tên lớp, package, mô-đun và giới hạn tài nguyên trong một chuỗi. Dùng **module/class-pattern** để ràng buộc mô-đun; dùng **.* ** cho package trực tiếp và **.**** cho cả subpackage; dùng **!** để từ chối; đặt các ngoại lệ trước rule cho phép rộng và thêm **!* ** để tạo allow-list nghiêm ngặt.

Bốn giới hạn **maxdepth**, **maxrefs**, **maxbytes** và **maxarray** kiểm soát độ sâu, số reference, lượng byte đã đọc và chiều dài mảng. Chúng được kiểm tra trước rule lớp. Hãy cấu hình filter cho đúng stream hoặc toàn JVM, hiểu trạng thái **UNDECIDED**, và kết hợp filtering với xác thực dữ liệu cùng policy riêng cho từng ngữ cảnh.
