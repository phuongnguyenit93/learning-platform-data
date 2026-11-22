# Enum evolution và khả năng tương thích trong Java

## 1. Enum thay đổi theo phiên bản: tại sao một thay đổi nhỏ có thể gây lỗi lớn?

`enum` mô tả một tập các hằng có tên, chẳng hạn trạng thái đơn hàng, trạng thái tác vụ hoặc loại sự kiện:

```java
enum JobStatus {
    NEW,
    RUNNING,
    DONE
}
```

Ban đầu hệ thống chỉ có ba trạng thái. Sau một thời gian, sản phẩm cần thêm `PAUSED` hoặc đổi tên `RUNNING` thành `IN_PROGRESS`. Nếu các module, file dữ liệu, database, API và thông điệp được triển khai ở **những thời điểm khác nhau**, thay đổi này có thể tác động đến mã đã được biên dịch trước đó và những dữ liệu đã tồn tại.

**Enum evolution** là quá trình thay đổi tập hằng hoặc hành vi của enum qua các phiên bản. **Khả năng tương thích** không chỉ có một nghĩa:

1. **Binary compatibility (tương thích nhị phân):** một file `.class` đã biên dịch với enum cũ vẫn có thể liên kết và chạy với enum mới hay không, xét theo quy tắc liên kết của Java.
2. **Source compatibility (tương thích mã nguồn):** mã nguồn client cũ có còn biên dịch được khi enum được đổi và client được biên dịch lại không.
3. **Behavioral compatibility (tương thích hành vi):** chương trình có còn trả về kết quả đúng về mặt nghiệp vụ cho các giá trị cũ và mới không.
4. **Data/wire compatibility (tương thích dữ liệu/giao thức):** những chuỗi hoặc số đã ghi vào database, JSON, message queue, cache, log, file cấu hình hay được dịch vụ khác gửi đến có được diễn giải đúng không.

Một thay đổi có thể **binary-compatible nhưng behaviorally breaking**. Đây là tình huống quan trọng nhất của việc thêm enum constant vào một `switch` exhaustive.

Đặc tả [JLS Java 21 §13.4.26](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.26) nêu rõ: **thêm hoặc đổi thứ tự enum constant không phá vỡ binary compatibility của các binary có trước**, nhưng việc thêm constant có thể khiến một `switch` exhaustive được biên dịch trước đó thất bại khi gặp giá trị mới. Vì vậy, từ “compatible” phải luôn đi kèm **loại compatibility** đang nói đến.

## 2. Những thành phần của enum dễ bị ảnh hưởng khi thay đổi

Với enum:

```java
enum JobStatus {
    NEW,
    RUNNING,
    DONE
}
```

Java cung cấp nhiều cách thao tác:

| Thành phần | Ý nghĩa | Tác động khi enum phát triển |
| --- | --- | --- |
| `JobStatus.NEW` | Trường `public static final` đại diện hằng `NEW` | Xóa/đổi tên `NEW` làm mã tham chiếu hằng cũ mất trường |
| `JobStatus.values()` | Mảng hằng theo **thứ tự khai báo hiện tại** | Thêm/xóa/reorder thay đổi độ dài và thứ tự mảng |
| `status.name()` | Tên định danh chính xác, như `"NEW"` | Không đổi khi chỉ reorder; đổi khi đổi tên hằng |
| `status.ordinal()` | Vị trí trong khai báo, bắt đầu từ `0` | Thay đổi khi chèn, xóa, reorder |
| `JobStatus.valueOf("DONE")` | Tìm hằng theo tên **khớp chính xác** | Tên không tồn tại gây `IllegalArgumentException` |
| `status.toString()` | Mặc định giống `name()`, nhưng có thể override | Không phải định danh bền vững nếu dùng để hiển thị |
| `switch(status)` | Chọn nhánh dựa trên hằng | Thêm hằng có thể tạo nhánh chưa xử lý |

`ordinal()` là một chỉ số nội bộ theo thứ tự khai báo, **không phải mã nghiệp vụ ổn định**. API `Enum.ordinal()` khuyến cáo phần lớn ứng dụng không cần tự gọi nó; các cấu trúc như `EnumSet` và `EnumMap` mới là nhóm sử dụng điển hình.

`name()` ổn định qua việc **đổi thứ tự**, nhưng **không** ổn định nếu đổi chính tên constant. Nếu một tên đã được công bố cho bên ngoài, việc đổi tên phải được coi là thay đổi giao thức hoặc schema, không đơn thuần là refactor mã Java.

## 3. Bảng tác động của các kiểu thay đổi enum thường gặp

| Thay đổi | Binary compatibility | Source compatibility | Rủi ro hành vi/dữ liệu |
| --- | --- | --- | --- |
| **Thêm** `PAUSED` vào cuối | Có theo JLS | `switch expression` exhaustive cũ có thể **không biên dịch** khi build lại | Consumer cũ có thể chưa biết `PAUSED`; persisted string mới không đọc được ở bản cũ |
| **Chèn** constant vào giữa | Có | Có điều kiện như việc thêm constant | `ordinal` của các hằng phía sau dịch chuyển |
| **Đổi thứ tự** constants | Có | Thường không đổi các tham chiếu bằng tên | `ordinal`, thứ tự `values()`, natural order thay đổi |
| **Xóa** `RUNNING` | Không bảo đảm, thường phá binary đang tham chiếu | Mã dùng `RUNNING` không biên dịch | `NoSuchFieldError`, dữ liệu tên cũ không giải mã được |
| **Đổi tên** `RUNNING` thành `IN_PROGRESS` | Về bản chất là xóa trường cũ, thêm trường mới | Tham chiếu tên cũ lỗi khi build lại | Giá trị lưu theo `name` và Java serialization cũ mất hằng tương ứng |
| **Đổi `toString()`** hoặc logic của hằng | Phụ thuộc kiểu thay đổi API cụ thể; có thể vẫn liên kết được | Có thể vẫn biên dịch | Hiển thị/API dùng `toString()` thay đổi kết quả |
| **Thêm trường `code` ổn định** mà giữ tên cũ | Tùy cấu trúc thay đổi, thường khả thi | Client cũ thường không cần sửa | Cần đảm bảo mã không trùng và mapping backward compatible |

Các mục “có” ở cột binary **không phải lời hứa mọi chức năng runtime đều an toàn**. Ví dụ, dù thêm `PAUSED` là binary-compatible, một binary cũ có `switch` exhaustive không có nhánh `PAUSED` vẫn có thể thất bại khi nhận `PAUSED`.

Quy tắc thực tế: **phân tích đồng thời ba đối tượng**: phiên bản mã enum, phiên bản mã consumer và dữ liệu đi qua ranh giới của hai phiên bản đó.

## 4. Thêm enum constant và tính exhaustive của `switch expression`

### 4.1. Phiên bản 1: mã đầy đủ, không cần `default`

```java
enum Status {
    NEW, DONE
}

static String label(Status status) {
    return switch (status) {
        case NEW -> "new";
        case DONE -> "done";
    };
}
```

Đây là một đoạn minh họa đặt trong ngữ cảnh Java hợp lệ. Với kiểu selector `Status` gồm đúng hai hằng, `switch expression` bao phủ toàn bộ constant mà compiler biết, nên **không bắt buộc có `default`**.

Không viết `default` có một lợi ích bảo trì: nó thể hiện kỳ vọng rằng **mọi constant phải được xử lý rõ ràng**.

### 4.2. Phiên bản 2: bổ sung `PAUSED`

```java
enum Status {
    NEW, PAUSED, DONE
}
```

Nếu biên dịch lại phương thức `label` ở trên với enum mới, Java sẽ báo lỗi dạng:

```text
the switch expression does not cover all possible input values
```

Vì `PAUSED` chưa có nhánh xử lý. Đây là **lỗi source compatibility** trong một consumer cụ thể (không phải mọi source file sử dụng enum đều sẽ lỗi).

Sửa trực tiếp:

```java
static String label(Status status) {
    return switch (status) {
        case NEW -> "new";
        case PAUSED -> "paused";
        case DONE -> "done";
    };
}
```

**Không nên chữa bằng `default` một cách máy móc** nếu `PAUSED` có hành vi nghiệp vụ riêng. `default` giúp biên dịch, nhưng cũng có thể che những constant mới sau này.

### 4.3. Nếu không biên dịch lại consumer cũ thì sao?

Xét một **consumer binary đã được biên dịch** khi enum chỉ có `NEW`, `DONE`, rồi được chạy với phiên bản enum có thêm `PAUSED`.

Theo JLS Java 21:

- Thêm constant vẫn là thay đổi **binary-compatible**.
- Nếu consumer nhận `PAUSED` và `switch expression` không có case nào áp dụng, runtime Java 21 có thể ném **`java.lang.MatchException`**.
- Việc không có `default` là cách để compiler buộc xử lý mỗi giá trị khi biên dịch lại, nhưng **không bảo đảm binary cũ chạy đúng với mọi giá trị mới khi được triển khai độc lập**.

**Lưu ý phiên bản:** kết quả lỗi runtime của `switch` exhaustive phát triển theo Java; trong các Java đời cũ từng có tình huống phát sinh `IncompatibleClassChangeError`. Với bài học và lab Java 21 này, dùng quy tắc `MatchException` của JLS Java 21 §15.28.2. Không khẳng định cùng một loại ngoại lệ cho mọi JDK đời cũ.

Một hệ thống thực tế có thể “load class thành công” và chỉ lỗi khi nhận giá trị `PAUSED`. Vì vậy cần test **consumer cũ + producer mới**, không chỉ kiểm tra ứng dụng có khởi động được hay không.

## 5. Lab separate compilation: nhìn rõ binary compatible nhưng runtime không tương thích

Thử nghiệm sau dùng **Java 21+**, với hai file Java ở cùng thư mục và một thư mục kết quả `classes`. Đây là lab có **hai phiên bản liên tiếp của cùng một file**; không ghép hai định nghĩa `Status` vào một chương trình.

**Bước A — Tạo `Status.java` phiên bản 1:**

```java
public enum Status {
    NEW, DONE
}
```

**Bước B — Tạo `Consumer.java` (giữ nguyên qua cả hai lần):**

```java
public class Consumer {
    static String label(Status status) {
        return switch (status) {
            case NEW -> "new";
            case DONE -> "done";
        };
    }

    public static void main(String[] args) {
        Status value = Status.valueOf(args[0]);
        System.out.println(label(value));
    }
}
```

Biên dịch cả hai file và chạy:

```bash
javac --release 21 -d classes Status.java Consumer.java
java -cp classes Consumer NEW
```

Đầu ra:

```text
new
```

**Bước C — Thay nội dung `Status.java` bằng phiên bản 2** (giữ `Consumer.java` y nguyên):

```java
public enum Status {
    NEW, PAUSED, DONE
}
```

Chỉ biên dịch **`Status.java`**, giữ file `Consumer.class` cũ:

```bash
javac --release 21 -d classes Status.java
java -cp classes Consumer PAUSED
```

Đây là thử nghiệm về **phối hợp binary cũ và enum mới**. Java 21 có thể ném `MatchException` khi consumer cũ gặp `PAUSED` ở `switch` exhaustive không có nhánh tương ứng. Trong một terminal, stack trace có thêm tên file/dòng; không dùng toàn bộ stack trace làm kết quả bất biến của bài.

**Bước D — Thử biên dịch lại consumer** với enum mới:

```bash
javac --release 21 -cp classes -d classes Consumer.java
```

Bây giờ compiler biết `PAUSED` và sẽ phát hiện `switch expression` chưa exhaustive, buộc sửa code. Đây là điểm hữu ích của việc **không có `default`** khi mỗi enum constant cần một hành vi riêng.

**Điều lab muốn kiểm chứng:**

| Tình huống | Hiệu ứng |
| --- | --- |
| Consumer v1 biên dịch với Status v1 | Thành công |
| Consumer v1 (đã biên dịch) chạy với Status v2, chỉ dùng `NEW`/`DONE` | Có thể vẫn hoạt động bình thường |
| Consumer v1 chạy với Status v2 và nhận `PAUSED` | Có thể lỗi runtime do thiếu case |
| Biên dịch lại Consumer v1 với Status v2 | Báo thiếu coverage trong `switch expression` |

Lab nói về `switch expression`, không được tự động áp dụng kết luận runtime y hệt cho **legacy `switch statement`**; mục sau giải thích khác biệt.

## 6. `switch statement` kiểu cũ có thể bỏ qua constant mới

Với `switch statement` truyền thống trên enum, compiler không bắt buộc `default`:

```java
enum Status {
    NEW, DONE, PAUSED
}

static void print(Status status) {
    switch (status) {
        case NEW -> System.out.println("new");
        case DONE -> System.out.println("done");
    }
}
```

Phương thức này **có thể biên dịch** dù thiếu `PAUSED`. Nếu gọi `print(Status.PAUSED)`, không có nhãn nào áp dụng, statement hoàn thành bình thường và **không in gì**.

Đó là một khác biệt cần ghi nhớ:

- **`switch expression`:** bắt buộc exhaustive; thiếu constant của enum hiện tại sẽ lỗi compile time.
- **Legacy `switch statement`:** không nhất thiết exhaustive; giá trị mới có thể bị bỏ qua im lặng.
- **Enhanced `switch statement`** của Java 21 (chẳng hạn dùng pattern label hoặc `case null`) có các yêu cầu exhaustiveness riêng, không đánh đồng với legacy statement.

Nếu muốn dùng switch statement nhưng không bỏ qua giá trị lạ, hãy thêm `default` xử lý rõ ràng:

```java
static void printStrict(Status status) {
    switch (status) {
        case NEW -> System.out.println("new");
        case DONE -> System.out.println("done");
        default -> throw new IllegalArgumentException(
            "Unhandled status: " + status
        );
    }
}
```

Khi chọn `default`, bạn đang chọn **chính sách fallback**. Nó có thể là chính sách tốt cho boundary với dữ liệu không kiểm soát, nhưng cũng làm compiler không còn buộc bạn cập nhật từng case khi enum được mở rộng.

## 7. `default`: bảo vệ vận hành hay che lỗi thiếu cập nhật?

Không có một quy tắc duy nhất rằng mọi enum `switch` đều phải hoặc đều không được dùng `default`.

**Không có `default`** phù hợp khi:
- Tập enum là một **closed domain** mà ứng dụng kiểm soát.
- Mỗi constant buộc phải có hành vi riêng.
- Khi thêm hằng, bạn **muốn compilation fail** cho đến khi code xử lý được cập nhật.
- Các module được biên dịch và triển khai đồng bộ tương đối tốt.

**Có `default`** phù hợp khi:
- Consumer phải tiếp tục hoạt động trước dữ liệu bất ngờ và có fallback được quy định rõ.
- Không thể cập nhật tất cả consumer cùng thời điểm.
- Giá trị mới có thể tạm thời được xử lý chung theo một chính sách.
- `default` ghi log, trả mã “unsupported” hoặc ném ngoại lệ được thiết kế trước thay vì làm việc sai im lặng.

Ví dụ fail-fast:

```java
static String labelStrict(Status value) {
    return switch (value) {
        case NEW -> "new";
        case DONE -> "done";
        default -> throw new IllegalStateException(
            "Unhandled status: " + value
        );
    };
}
```

Nhánh `default` này vẫn phải được test, vì compiler sẽ không yêu cầu bạn thêm case mới khi bổ sung `PAUSED`.

Ví dụ fallback có chủ đích:

```java
static String labelForUi(Status value) {
    return switch (value) {
        case NEW -> "New";
        case DONE -> "Done";
        default -> "Unsupported status";
    };
}
```

Nếu UI có thể hiển thị `Unsupported status` mà không làm sai trạng thái giao dịch, đây là lựa chọn hợp lý. Nhưng trong xử lý thanh toán hoặc nghiệp vụ nhạy cảm, việc gom mọi trạng thái không biết thành một nhánh mặc định có thể là nguy hiểm về logic; hãy đưa ra chính sách riêng cho loại hành vi đó.

## 8. Đổi thứ tự constant: binary-compatible nhưng `ordinal` đổi nghĩa

Giả sử v1:

```java
enum Stage {
    NEW, RUNNING, DONE
}
```

Thì:

```text
NEW.ordinal()     = 0
RUNNING.ordinal() = 1
DONE.ordinal()    = 2
```

Sau khi reorder:

```java
enum Stage {
    DONE, NEW, RUNNING
}
```

Thì:

```text
DONE.ordinal()    = 0
NEW.ordinal()     = 1
RUNNING.ordinal() = 2
```

Theo JLS, reorder là **binary-compatible**, vì các hằng có tên vẫn tồn tại. Nhưng một database từng lưu số `0` với nghĩa `NEW` và mã mới đọc nó bằng `Stage.values()[0]` sẽ lấy **`DONE`**: dữ liệu bị diễn giải sai mà không nhất thiết phát sinh lỗi.

Hệ quả của việc reorder hoặc chèn constant:
- `ordinal()` và chỉ số `values()[i]` thay đổi.
- `values()` trả hằng theo thứ tự khai báo mới.
- `Enum.compareTo()` và thứ tự tự nhiên của enum dựa trên vị trí khai báo, nên kết quả sắp xếp có thể đổi.
- `EnumSet` và `EnumMap` biểu diễn/duyệt các hằng theo thứ tự tự nhiên của enum, có thể đổi thứ tự lặp.
- Mã dựa vào “constant đầu tiên”, “constant cuối cùng” hoặc thứ tự enum như mức ưu tiên có thể đổi hành vi.

**Không dùng `ordinal` làm khóa lưu trữ, mã API hoặc dữ liệu lịch sử.** Nó thích hợp cho cơ chế nội bộ của enum và một số collection chuyên dụng, không phải hợp đồng dữ liệu bền vững giữa các phiên bản.

Mô phỏng so sánh hai phiên bản bằng hai enum **riêng biệt**:

```java
enum Before { NEW, RUNNING, DONE }
enum Reordered { DONE, NEW, RUNNING }

System.out.println(Before.NEW.ordinal());    // 0
System.out.println(Reordered.NEW.ordinal()); // 1
```

Hai enum trên khác kiểu trong cùng một chương trình; chúng chỉ **mô phỏng sự khác biệt thứ tự giữa hai version**, không phải thực sự chạy hai binary của cùng một enum.

## 9. Đổi tên hoặc xóa constant: nguy cơ source, binary và dữ liệu

Thay đổi từ:

```java
enum Status {
    NEW, RUNNING, DONE
}
```

sang:

```java
enum Status {
    NEW, IN_PROGRESS, DONE
}
```

nhìn như một rename đơn giản, nhưng với Java, mỗi enum constant tương ứng với một trường `public static final`. Phiên bản mới đã **xóa trường `RUNNING`** và thêm trường `IN_PROGRESS`.

Hệ quả:

- **Biên dịch lại source cũ:** tham chiếu `Status.RUNNING` hoặc nhãn `case RUNNING` sẽ lỗi vì tên không còn.
- **Binary cũ:** một binary đã biên dịch mà vẫn tham chiếu trực tiếp trường `RUNNING` có thể ném **`NoSuchFieldError`** khi liên kết/thực thi phần code liên quan.
- **Chuỗi đã lưu:** `Status.valueOf("RUNNING")` sẽ ném `IllegalArgumentException` vì enum mới không còn hằng tên đó.
- **Dữ liệu truyền qua API:** consumer cũ không biết `IN_PROGRESS`, trong khi consumer mới không biết `RUNNING` nếu không có cơ chế chuyển tiếp.
- **Java object serialization:** enum được serialize bằng tên constant; đổi/xóa tên có thể phá khả năng deserialize dữ liệu lịch sử.

**Rename không phải thay đổi binary-compatible** chỉ vì IDE có chức năng “Rename Symbol”. Công cụ IDE chỉ sửa các vị trí trong cùng phạm vi source mà nó kiểm soát; nó không tự đổi tên trong database, message queue, dữ liệu archive, hợp đồng API của dịch vụ khác hoặc binary đã phát hành.

### Cách chuyển tiếp an toàn hơn: giữ constant cũ tạm thời

```java
enum Status {
    NEW,
    RUNNING,      // tên cũ, giữ trong giai đoạn chuyển tiếp
    IN_PROGRESS,  // tên mới
    DONE
}
```

Nếu dùng cả hai constant, phải xác định quy tắc ánh xạ và thời điểm ngừng phát `RUNNING`. Chẳng hạn chỉ sinh `IN_PROGRESS` cho dữ liệu mới, nhưng vẫn nhận `RUNNING` từ consumer cũ. Tuy nhiên, **hai constant này là hai đối tượng enum khác nhau**: `RUNNING != IN_PROGRESS`, nên không thể chỉ thêm hằng mới rồi nghĩ chúng tự tương đương. Cần explicit mapping ở nơi xử lý và ở các `switch` liên quan.

Một chiến lược khác là giữ nguyên Java constant `RUNNING` để duy trì tương thích mã và chỉ đổi **nhãn hiển thị** hoặc **mã wire** qua trường riêng. Cách này thường ít rủi ro hơn nếu việc rename chỉ phục vụ giao diện/ngôn ngữ nghiệp vụ.

## 10. `name()`, `valueOf()`, `toString()` và serialization

### 10.1. `name()` là tên định danh, không phải nhãn người dùng

```java
enum Status { NEW, RUNNING, DONE }

System.out.println(Status.RUNNING.name()); // RUNNING
```

`name()` là final và trả đúng tên khai báo. Nó không bị ảnh hưởng bởi reorder, nhưng bị ảnh hưởng trực tiếp nếu đổi tên hằng.

`toString()` mặc định trả tên, nhưng enum có thể override `toString()` để hiển thị thân thiện:

```java
enum Status {
    NEW, RUNNING, DONE;

    @Override
    public String toString() {
        return switch (this) {
            case NEW -> "New job";
            case RUNNING -> "In progress";
            case DONE -> "Completed";
        };
    }
}
```

Với enum này, `RUNNING.toString()` trả `"In progress"` còn `RUNNING.name()` vẫn trả `"RUNNING"`. Không dùng `toString()` như một định danh lưu trữ nếu nó được tự do thay đổi theo ngôn ngữ, bản dịch hoặc yêu cầu UI.

### 10.2. `valueOf()` yêu cầu tên chính xác

```java
Status.valueOf("DONE");  // DONE

// Ném IllegalArgumentException nếu enum không có hằng tương ứng:
// Status.valueOf("PAUSED");
```

`valueOf()` phân biệt chữ hoa/chữ thường; không tự trim khoảng trắng, không tự chuyển tên cũ sang tên mới. Nếu dữ liệu đến từ người dùng, từ API hoặc database nhiều phiên bản, phải có lớp **parse/normalize/migration** thay vì gọi `valueOf` mà không kiểm soát lỗi.

### 10.3. Java serialization chuẩn của enum dùng **tên**, không phải ordinal

Đặc tả Java Object Serialization, §1.12, nêu rằng enum constant khi serialize bằng `ObjectOutputStream` được biểu diễn theo **tên hằng**. Khi deserialize, hệ thống dùng tên để tìm enum constant tương ứng.

Điều đó có nghĩa:
- Chỉ reorder constants thường không làm tên đã serialize mất hiệu lực.
- Đổi tên hoặc xóa constant có thể làm dữ liệu Java serialization cũ không được giải mã theo cách bình thường.
- Không thể tùy biến cơ chế serializing enum bằng các hook `writeObject/readObject` thông thường như với class tùy ý.

**Không suy rộng** kết luận này sang mọi thư viện JSON, protobuf, ORM hay hệ thống binary serialization khác. Mỗi framework và cấu hình có thể serialize enum bằng **tên, số, mã tùy chỉnh hoặc định dạng riêng**. Phải kiểm tra serializer thực tế đang dùng.

## 11. Thiết kế mã wire ổn định, tách khỏi tên hằng

Khi enum được lưu hoặc trao đổi qua phiên bản, dùng **mã nghiệp vụ ổn định** thường tốt hơn dùng `ordinal` và có thể tốt hơn dùng `name()` nếu tên Java có khả năng refactor.

```java
enum Status {
    NEW("new"),
    RUNNING("running"),
    DONE("done");

    private final String code;

    Status(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Ở đây:
- `Status.RUNNING.name()` là `"RUNNING"`.
- `Status.RUNNING.code()` là `"running"`.
- Mã `"running"` được coi là **contract với dữ liệu ngoài**, nên cần giữ ổn định hoặc có alias migration nếu phải đổi.
- Thứ tự khai báo và `ordinal` có thể đổi mà mã wire không đổi.

**Mã ổn định không có nghĩa tự động tương thích.** Nếu phiên bản cũ không biết mã `"paused"`, nó vẫn cần chính sách xử lý unknown value. Mã riêng chỉ giúp tránh phụ thuộc vào rename và ordinal.

### Parser có thể nhận alias của phiên bản cũ

```java
static java.util.Optional<Status> parseCode(String raw) {
    if (raw == null) {
        return java.util.Optional.empty();
    }

    String code = raw.strip().toLowerCase(java.util.Locale.ROOT);

    return switch (code) {
        case "new" -> java.util.Optional.of(Status.NEW);
        case "running", "in-progress" ->
            java.util.Optional.of(Status.RUNNING);
        case "done", "finished" ->
            java.util.Optional.of(Status.DONE);
        default -> java.util.Optional.empty();
    };
}
```

Parser minh họa này đặt trong một class có enum `Status` ở trên, hoặc dùng file đầy đủ ở mục sau. Nó:

1. Xử lý `null` mà không ném `NullPointerException`.
2. Chuẩn hóa khoảng trắng và chữ hoa/chữ thường bằng `Locale.ROOT`.
3. Nhận các alias legacy như `"in-progress"` hoặc `"finished"`.
4. Trả `Optional.empty()` với mã chưa biết để caller quyết định log, từ chối hay fallback.
5. Không gán một mã lạ thành một trạng thái bất kỳ, tránh vô tình xử lý sai nghiệp vụ.

**Quan trọng:** một alias như `"in-progress"` phải được tài liệu hóa cùng nghĩa với `RUNNING` tại boundary; không tự coi mọi tên giống nhau là tương đương nếu logic nghiệp vụ đã thay đổi.

## 12. Chương trình Java 17 chạy được: name, ordinal, alias, exhaustive switch

Lưu file **`EnumEvolutionDemo.java`**:

```java
public class EnumEvolutionDemo {
    enum Status {
        NEW("new"),
        RUNNING("running"),
        DONE("done");

        private final String code;

        Status(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    // Hai enum chỉ mô phỏng thứ tự của hai phiên bản khác nhau.
    enum Before { NEW, RUNNING, DONE }
    enum Reordered { DONE, NEW, RUNNING }

    static String label(Status s) {
        return switch (s) {
            case NEW -> "New";
            case RUNNING -> "In progress";
            case DONE -> "Done";
        };
    }

    static java.util.Optional<Status> parseCode(String raw) {
        if (raw == null) {
            return java.util.Optional.empty();
        }

        String code = raw.strip().toLowerCase(java.util.Locale.ROOT);

        return switch (code) {
            case "new" -> java.util.Optional.of(Status.NEW);
            case "running", "in-progress" ->
                java.util.Optional.of(Status.RUNNING);
            case "done", "finished" ->
                java.util.Optional.of(Status.DONE);
            default -> java.util.Optional.empty();
        };
    }

    public static void main(String[] args) {
        for (Status s : Status.values()) {
            System.out.println(
                s.name() + ":ordinal=" + s.ordinal()
                + ",code=" + s.code()
            );
        }

        System.out.println("label=" + label(Status.RUNNING));
        System.out.println("legacy=" + parseCode("in-progress"));
        System.out.println("unknown=" + parseCode("paused"));
        System.out.println("valueOf=" + Status.valueOf("DONE"));

        System.out.println(
            "Before.NEW.ordinal=" + Before.NEW.ordinal()
        );
        System.out.println(
            "Reordered.NEW.ordinal=" + Reordered.NEW.ordinal()
        );
        System.out.println(
            "Before.DONE.ordinal=" + Before.DONE.ordinal()
        );
        System.out.println(
            "Reordered.DONE.ordinal=" + Reordered.DONE.ordinal()
        );
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 EnumEvolutionDemo.java
java EnumEvolutionDemo
```

Đầu ra:

```text
NEW:ordinal=0,code=new
RUNNING:ordinal=1,code=running
DONE:ordinal=2,code=done
label=In progress
legacy=Optional[RUNNING]
unknown=Optional.empty
valueOf=DONE
Before.NEW.ordinal=0
Reordered.NEW.ordinal=1
Before.DONE.ordinal=2
Reordered.DONE.ordinal=0
```

Phân tích:

- Ba dòng đầu chứng minh `name()`, `ordinal()` và `code()` không đồng nhất.
- `label` dùng `switch expression` exhaustive, không có `default`, bởi ba constant đều được xử lý.
- `legacy=Optional[RUNNING]` chứng minh một chuỗi alias cũ có thể ánh xạ về trạng thái hiện tại theo chính sách rõ ràng.
- `unknown=Optional.empty` cho thấy parser không giả định mọi mã từ bên ngoài đều hợp lệ.
- Các dòng `Before`/`Reordered` minh họa `ordinal` thay đổi dù **tên** `NEW`, `DONE` được giữ nguyên.

Ví dụ này không yêu cầu Java 21, vì `switch expression` được hỗ trợ chính thức trước Java 17. Nó phù hợp để học riêng phần **enum và constant** ngay cả khi chưa sử dụng pattern `switch`.

## 13. Enum trong pattern `switch` trên interface/sealed type (Java 21+)

Java 21 cho phép `switch` với selector là một **reference type**, không nhất thiết là enum cụ thể. Trong một số trường hợp, nhãn enum constant có thể được viết với tên enum đủ điều kiện, như `case Status.NEW`, để phân biệt hằng của enum thực hiện một interface.

```java
sealed interface Event permits Status, Fault {}

enum Status implements Event {
    NEW, DONE
}

record Fault(String message) implements Event {}
```

Với selector tĩnh là `Event`, một pattern `switch` có thể dùng các nhãn:

```java
static String describe(Event event) {
    return switch (event) {
        case Status.NEW -> "new";
        case Status.DONE -> "done";
        case Fault f -> "fault:" + f.message();
    };
}
```

Vì `Event` là sealed và enum `Status` hiện chỉ có hai hằng, tập nhãn này có thể được compiler xem là exhaustive. Nếu thêm một hằng mới vào `Status` và biên dịch lại mã này, bạn cần đánh giá lại coverage, tương tự quy tắc mở rộng enum ở trên.

**Chương trình Java 21 độc lập**, file `EnumPatternIntegrationDemo.java`:

```java
public class EnumPatternIntegrationDemo {
    sealed interface Event permits Status, Fault {}

    enum Status implements Event {
        NEW, DONE
    }

    record Fault(String message) implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case Status.NEW -> "new";
            case Status.DONE -> "done";
            case Fault f -> "fault:" + f.message();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Status.NEW));
        System.out.println(describe(Status.DONE));
        System.out.println(describe(new Fault("offline")));

        try {
            System.out.println(describe(null));
        } catch (NullPointerException ex) {
            System.out.println("null => NPE");
        }
    }
}
```

Chạy:

```bash
javac --release 21 EnumPatternIntegrationDemo.java
java EnumPatternIntegrationDemo
```

Kết quả:

```text
new
done
fault:offline
null => NPE
```

Điểm rút ra:

- `case Status.NEW` và `case Status.DONE` là các **enum constant labels**; `case Fault f` là type pattern.
- `Fault` được xử lý qua pattern variable `f`.
- `null` không được một nhãn trên tiếp nhận, nên `NullPointerException` được bắt trong `main`.
- Pattern `switch` Java 21 bổ sung khả năng phân loại nhiều kiểu qua interface/sealed hierarchy; nguyên tắc **enum evolution làm thay đổi coverage** vẫn cần được tôn trọng.

Không nhầm yêu cầu phiên bản: ví dụ mục 12 dùng Java 17, còn ví dụ này dùng cú pháp pattern `switch` Java 21+.

## 14. Khi triển khai nhiều dịch vụ: consumer cũ và producer mới

Giả sử dịch vụ A (producer) có thể phát các trạng thái của đơn hàng và dịch vụ B (consumer) đọc chúng. Ban đầu cả hai biết `NEW`, `DONE`. Sau đó A bắt đầu gửi `PAUSED`.

Nếu B vẫn chạy phiên bản cũ:
- Parser gọi `Status.valueOf("PAUSED")` có thể ném `IllegalArgumentException`.
- Parser `Optional` trả unknown thì dịch vụ B có thể xử lý theo chính sách định trước: ghi nhận, trả về mã lỗi hỗ trợ, đưa message vào dead-letter queue, hoặc lưu lại để xử lý sau.
- Nếu dữ liệu mới đã được chuyển thành một đối tượng enum Java của phiên bản mới nhưng logic `switch` thuộc binary cũ, vẫn tồn tại rủi ro nhánh chưa biết như ở mục 4.
- Nếu B chỉ có legacy `switch statement` không `default`, trạng thái mới có thể bị bỏ qua mà không ai biết.

Vì vậy, thứ tự rollout cần dựa vào **mức sẵn sàng của consumer**, không chỉ khả năng producer phát enum mới.

### Một quy trình rollout an toàn hơn

1. **Chuẩn bị consumer:** phát hành parser hoặc logic có khả năng nhận/ghi nhận unknown value; kiểm tra các đường xử lý không làm sai trạng thái.
2. **Thống nhất mã wire:** thêm mapping bền vững, ví dụ `"paused"`, và mô tả ý nghĩa ở schema/API contract.
3. **Cập nhật tất cả switch liên quan:** quyết định nhánh cụ thể hay fallback, test cả switch expression lẫn statement.
4. **Triển khai logic consumer trước khi phát dữ liệu mới**, khi có thể.
5. **Bật phát giá trị mới một cách có kiểm soát**, theo dõi metric/log của mã unknown.
6. **Duy trì alias cho tên cũ trong giai đoạn chuyển đổi** và chỉ loại bỏ khi chắc chắn không còn bên nào cần.
7. **Biên dịch/test lại các module liên quan**, tránh chạy các binary không được đồng bộ với bộ enum hiện tại.

“Thêm enum constant là binary-compatible” **không** có nghĩa producer có thể gửi dữ liệu mới vào bất kỳ phiên bản consumer cũ nào mà không cần chuẩn bị.

## 15. Migration dữ liệu đã lưu

### 15.1. Nếu đã lưu `ordinal`

Ví dụ database chứa:

```text
status_ordinal
0
1
2
```

Khi v1 là `NEW, RUNNING, DONE`, các số tương ứng lần lượt là `NEW, RUNNING, DONE`. Sau reorder thành `DONE, NEW, RUNNING`, nếu đọc bằng `values()[ordinal]` thì ý nghĩa bị đảo lộn.

**Cách migration:**
1. Xác định rõ **version lịch sử** tương ứng với từng row/batch dữ liệu.
2. Dùng bảng ánh xạ **cố định theo ý nghĩa version cũ**, ví dụ `0 -> "new"`, `1 -> "running"`, `2 -> "done"`.
3. Chuyển dữ liệu sang **mã ổn định** có schema riêng thay vì chỉ số enum hiện hành.
4. Xác minh tổng số row, thống kê phân phối trạng thái trước/sau và chạy kiểm thử ứng dụng đọc lại.
5. Chỉ bỏ cách đọc legacy khi chắc chắn không còn dữ liệu dạng ordinal.

Không viết migration bằng `Status.values()[oldOrdinal]` của **phiên bản mới**: nó sẽ tái tạo chính vấn đề bạn muốn sửa.

### 15.2. Nếu đã lưu `name()` hoặc chuỗi constant

Nếu database lưu `"RUNNING"` nhưng enum mới chỉ còn `IN_PROGRESS`, bạn cần:
- Giữ alias ở lớp đọc: `"RUNNING" -> IN_PROGRESS`.
- Hoặc migrate dữ liệu đã lưu theo mapping được duyệt.
- Tính cả event lưu trong queue, file backup, cấu hình, dữ liệu cache, log replay và downstream API nếu chúng được parse lại.
- Xác định khi nào loại bỏ alias cũ sau khi tất cả producer/consumer đã chuyển đổi.

Không chỉ sửa trong ứng dụng mới và bỏ qua dữ liệu lịch sử: một record cũ đọc lại nhiều tháng sau vẫn có thể mang tên constant cũ.

### 15.3. Nếu sử dụng Java serialization chuẩn

Java serialization mặc định của enum dựa trên **tên hằng** chứ không dựa trên ordinal. Điều này tránh một kiểu hỏng do reorder, nhưng **không** bảo vệ bạn trước rename/remove.

Với hệ thống lưu trữ dài hạn hoặc giao tiếp dịch vụ, cân nhắc một schema độc lập và cơ chế migration rõ ràng thay vì phụ thuộc vào Java object serialization làm định dạng dữ liệu bền vững.

## 16. Checklist phân tích compatibility trước khi sửa enum

Khi có pull request thêm, xóa, đổi tên hoặc reorder enum, lần lượt kiểm tra:

1. **Constant nào thay đổi?** Thêm, xóa, rename, reorder hay chỉ thay metadata?
2. **Ai là consumer?** Mã cùng repository, thư viện đã phát hành, plugin bên thứ ba, REST/JSON, queue, batch job, persistence?
3. **Các consumer đã được biên dịch với enum phiên bản nào?** Có khả năng nhiều bản `.class` cùng chạy trên những môi trường khác nhau không?
4. **Các `switch expression` đã exhaustive chưa?** Nếu thêm constant, biên dịch lại consumer để phát hiện nhánh thiếu.
5. **Có `switch statement` nào thiếu `default` không?** Nó có thể bỏ qua constant mới khi chạy.
6. **Có `default` quá rộng không?** Nó có đang che một yêu cầu xử lý riêng hay hành vi nguy hiểm không?
7. **Có `ordinal()`, `values()[i]` hoặc thứ tự natural order được dùng làm dữ liệu không?** Reorder có thể làm sai kết quả.
8. **Có serialize bằng tên hoặc số không?** Xem chính xác serializer/framework đang dùng.
9. **Có direct field references đến constant sắp xóa không?** Có thể gặp `NoSuchFieldError` ở binary cũ.
10. **Có `valueOf` với chuỗi đến từ bên ngoài không?** Cần xử lý unknown/legacy.
11. **Có migration và alias chính thức không?** Test lại dữ liệu lịch sử, cache/queue, backup.
12. **Test được các cặp phiên bản không?** Consumer cũ với producer mới; consumer mới với dữ liệu cũ; rebuild source; runtime binary; dữ liệu persisted.

### Ma trận kiểm thử thực tế

| Cặp phiên bản | Cần quan sát |
| --- | --- |
| Consumer v1 + enum v1 | Baseline: xử lý các constant ban đầu |
| Consumer v1 + enum v2 (không rebuild) | Link/load binary, `switch` gặp constant mới, parser của dữ liệu mới |
| Consumer v1 source + enum v2 (rebuild) | Lỗi exhaustive hoặc tham chiếu tên cũ |
| Consumer v2 + dữ liệu v1 | Alias, deserialization, migration hoạt động? |
| Consumer v2 + enum v2 | Xử lý đầy đủ cả constant mới và cũ |
| Consumer v2 + dữ liệu lạ | Chính sách unknown có an toàn, rõ ràng và quan sát được? |

Kiểm thử **binary cũ với enum mới** và **source cũ biên dịch lại với enum mới** là hai kịch bản khác nhau; không nên chỉ chạy unit test sau khi toàn bộ source đã rebuild.

## 17. Những sai lầm phổ biến

**Sai lầm 1: “Thêm enum constant là thay đổi không phá tương thích ở mọi nghĩa.”**  
Sai. JLS đảm bảo binary compatibility theo nghĩa cụ thể; `switch` exhaustive hoặc consumer chưa biết mã mới vẫn có thể lỗi.

**Sai lầm 2: “Đổi thứ tự enum không ảnh hưởng gì.”**  
Sai nếu hệ thống dùng `ordinal`, `values()[i]`, natural order hoặc thứ tự duyệt `EnumSet`/`EnumMap` làm ngữ nghĩa nghiệp vụ.

**Sai lầm 3: “Rename constant chỉ là refactor tên.”**  
Sai với binary đã phát hành và dữ liệu bên ngoài; nó tương đương xóa trường cũ và thêm trường mới ở cấp API.

**Sai lầm 4: “`default` trong switch luôn là best practice.”**  
Không nhất thiết. Nó có thể che việc thiếu xử lý constant mới; lựa chọn dựa trên contract.

**Sai lầm 5: “Không dùng `default` thì runtime sẽ không bao giờ có trạng thái lạ.”**  
Sai khi binary và enum được cập nhật độc lập. Java 21 có thể ném `MatchException` lúc gặp giá trị mới.

**Sai lầm 6: “Legacy `switch statement` tự biết enum đã được mở rộng.”**  
Không. Nó có thể không thực hiện gì khi gặp constant mới và không có nhánh áp dụng.

**Sai lầm 7: “`name()` là mã wire không bao giờ đổi.”**  
Nó chỉ giữ nguyên khi **tên constant vẫn giữ nguyên**; rename làm thay đổi dữ liệu string.

**Sai lầm 8: “`toString()` là định danh ổn định.”**  
Nó có thể override và thay theo yêu cầu hiển thị. Tránh dùng làm khóa nghiệp vụ nếu không có contract rõ.

**Sai lầm 9: “Java object serialization enum dùng ordinal.”**  
Không. Serialization chuẩn của Java dùng tên enum constant. Nhưng thư viện khác có thể chọn biểu diễn bằng số.

**Sai lầm 10: “`Enum.valueOf` sẽ trả `null` khi không có hằng.”**  
Sai. Nó ném `IllegalArgumentException` nếu không tìm thấy tên; phải bắt/ánh xạ đúng hoặc dùng parser trả `Optional`.

**Sai lầm 11: “Dữ liệu cũ có thể map bằng ordinal của enum mới.”**  
Sai nếu thứ tự đã đổi. Migration cần mapping dựa trên **schema lịch sử**, không dựa trên enum hiện hành.

**Sai lầm 12: “Triển khai producer mới trước là đủ vì enum binary-compatible.”**  
Sai ở giao diện liên dịch vụ. Consumer cũ có thể không parse hoặc không xử lý được constant mới.

## 18. Bài tập và đáp án

**Câu 1.** V1 có `enum State { NEW, DONE }`. V2 thêm `PAUSED`. Một consumer v1 chứa `switch expression` liệt kê hai hằng cũ nhưng không có `default`. Điều gì có thể xảy ra?

*Đáp án:* Khi rebuild consumer với v2, compiler báo thiếu nhánh. Nếu giữ binary cũ và chạy cùng enum v2, khi nhận `PAUSED`, trên Java 21 có thể ném `MatchException`. Thêm constant không phá binary compatibility theo JLS nhưng chưa bảo đảm behavior compatibility.

**Câu 2.** Chuyển thứ tự `{NEW, DONE}` thành `{DONE, NEW}` có ảnh hưởng `name()` không? `ordinal()` thì sao?

*Đáp án:* `name()` của `NEW` vẫn là `"NEW"`; `ordinal()` của `NEW` đổi từ `0` thành `1`. Dữ liệu lưu bằng ordinal có thể bị hiểu sai.

**Câu 3.** Vì sao đổi `RUNNING` thành `IN_PROGRESS` có thể gây `NoSuchFieldError`?

*Đáp án:* Constant enum là một trường `public static final` trong class enum. Một binary cũ vẫn tham chiếu trường `RUNNING`, nhưng enum mới không còn trường đó.

**Câu 4.** `Status.valueOf("paused")` có tự map đến `PAUSED` hoặc trả `null` không?

*Đáp án:* Không. `valueOf` cần tên khớp chính xác, ví dụ `"PAUSED"` khi enum có hằng đó; không có hằng sẽ ném `IllegalArgumentException`. Cần parser có normalization/alias/unknown policy nếu input là dữ liệu bên ngoài.

**Câu 5.** Một legacy `switch statement` trên enum có thiếu `default` nhưng vẫn biên dịch. Khi nhận constant mới không có case thì sao?

*Đáp án:* Statement có thể hoàn thành bình thường mà không chạy nhánh nào. Đây là rủi ro xử lý im lặng, khác với `switch expression` exhaustive.

**Câu 6.** Java serialization chuẩn của enum ghi `ordinal` hay `name`?

*Đáp án:* Ghi tên enum constant; vì vậy reorder không làm tên thay đổi, nhưng rename/remove có thể ảnh hưởng đến deserialization.

**Câu 7.** Có nên thêm `default -> "UNKNOWN"` vào mọi `switch` không?

*Đáp án:* Không theo quy tắc tuyệt đối. Dùng khi fallback đúng contract; bỏ `default` khi cần compiler bắt buộc xử lý explicit mọi enum constant mới. Cả hai cách đều cần test runtime và dữ liệu nhiều phiên bản.

**Câu 8.** Một hệ thống dùng mã `"running"` trong database và enum Java đổi từ `RUNNING` sang `IN_PROGRESS`. Làm sao giảm rủi ro?

*Đáp án:* Giữ mã wire ổn định `"running"` nếu ý nghĩa không đổi, hỗ trợ alias legacy nếu cần đổi mã, triển khai consumer hỗ trợ trước khi producer phát mã mới, migrate dữ liệu lịch sử có kiểm thử, và xử lý các binary cũ còn tham chiếu tên Java `RUNNING`.

## 19. Kết luận cần nhớ

- **Thêm/reorder constant:** JLS xem là binary-compatible, nhưng vẫn có thể phá source exhaustiveness, thứ tự dữ liệu hoặc hành vi `switch` runtime.
- **Xóa/rename constant:** có thể phá tham chiếu trường trong binary, mã nguồn, `valueOf` và dữ liệu đã serialize theo tên.
- **`ordinal` không phải mã lưu trữ bền vững**; `name` ổn định hơn khi reorder nhưng vẫn phụ thuộc tên khai báo.
- **`switch expression` exhaustive** giúp phát hiện thiếu case lúc rebuild; binary cũ vẫn cần kiểm tra khi chạy với enum mới.
- **Legacy `switch statement`** có thể bỏ qua giá trị mới nếu không có case/default.
- **Chính sách tiến hóa an toàn:** thiết kế mã wire ổn định, alias/migration cho dữ liệu cũ, xử lý unknown, test các cặp version và triển khai consumer trước producer khi có thể.

**Nguyên tắc lõi:** *Tương thích nhị phân chỉ trả lời rằng mã máy cũ có thể liên kết với kiểu mới; tính đúng đắn của `switch`, parser và dữ liệu phải được kiểm tra riêng qua toàn bộ vòng đời của enum.*

### Tài liệu chính thức

- [Java SE 21 JLS §13.4.26 — Evolution of Enum Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.26)
- [Java SE 21 JLS §14.11 — Switch Statement và exhaustiveness](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §15.28.2 — Run-Time Evaluation of switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.2)
- [Java SE 17 API — java.lang.Enum: name, ordinal, valueOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html)
- [Java Object Serialization Specification §1.12 — Serialization of Enum Constants](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/serial-arch.html#serialization-of-enum-constants)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
