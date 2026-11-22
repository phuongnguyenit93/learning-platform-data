# Giới hạn tác dụng phụ và tình trạng hoàn tất một phần

Java Stream API khuyến khích mô tả **dữ liệu cần biến đổi** thay vì điều khiển thủ công từng vòng lặp. Các thao tác như `filter`, `map`, `flatMap`, `reduce` và `collect` dễ kết hợp, hỗ trợ xử lý lazy và trong một số trường hợp có thể chạy song song. Nhưng chính sự linh hoạt đó khiến những **tác dụng phụ** (*side effects*)—ghi cơ sở dữ liệu, gửi HTTP, cập nhật biến ngoài pipeline, in log hoặc ghi tệp—trở nên nguy hiểm nếu bị xem như một phần tất yếu, luôn được thực hiện đúng một lần.

Đặc biệt, **Stream không phải transaction manager**. Nếu một phần tử làm phát sinh ngoại lệ giữa lúc xử lý, những thay đổi đã ghi ra hệ thống bên ngoài **không tự được rollback**. Với parallel stream, các tác vụ khác còn có thể đang thực thi khi một lỗi được quan sát. Kết quả cuối chưa được trả về **không có nghĩa** mọi tác dụng phụ trước đó đều chưa xảy ra.

Bài thuộc chương **Ngoại lệ và tính an toàn** của module **JAVA_STREAM_API**. Mục tiêu là giới hạn side effect đúng chỗ, hiểu việc dừng sớm và lỗi làm pipeline chỉ hoàn thành một phần, phân biệt mutable reduction hợp lệ với shared mutable state không an toàn, và thiết kế các ranh giới commit có thể kiểm chứng. Kiến thức liên quan tới grouping, collector tùy chỉnh, `Spliterator`, xử lý song song, tài nguyên I/O và cả các pipeline hiện đại dùng Stream Gatherers.

## 1. Ba khái niệm không được đánh đồng

| Khái niệm | Nghĩa | Ví dụ |
|---|---|---|
| **Tác dụng phụ** | Tác động có thể quan sát được bên ngoài giá trị trả về của hàm | `writer.write`, `db.insert`, sửa `List` bên ngoài, tăng counter |
| **Hoàn tất một phần** | Một số bước đã có tác động, trong khi toàn bộ tác vụ chưa hoàn tất như kỳ vọng | Ghi thành công 2 dòng rồi parse dòng 3 ném lỗi |
| **Tính nguyên tử** | Tác vụ được công bố như một đơn vị thành công/thất bại theo giao thức đã thiết kế | Commit một transaction hoặc công bố tệp đã chuẩn bị |

Một pipeline có thể **trả về giá trị đúng** nhưng vẫn gây tác dụng phụ ngoài ý muốn. Ngược lại, một pipeline **ném ngoại lệ** có thể đã ghi một phần kết quả vào tệp hoặc database.

### 1.1. Ví dụ tình trạng hoàn tất một phần

Giả sử đơn hàng lần lượt là `O1, O2, O3, O4`:

```text
O1 -> gọi API thành công       [tác dụng phụ đã xảy ra]
O2 -> gọi API thành công       [tác dụng phụ đã xảy ra]
O3 -> gọi API ném ngoại lệ     [pipeline thất bại]
O4 -> chưa được xử lý         [với cách duyệt tuần tự cụ thể]

Lệnh collect/forEach thất bại
         |
         +-- KHÔNG tự gọi API hoàn tác O1 và O2
         +-- KHÔNG trả kết quả "đã xử lý đủ bốn đơn"
```

Nếu retry **toàn bộ pipeline** mà không có cơ chế chống trùng, O1 và O2 có thể bị gửi **hai lần**. Lỗi không nằm ở riêng `forEach` mà ở việc kết hợp một phép duyệt dữ liệu với **hành động ngoài hệ thống không có ranh giới commit/retry**.

## 2. Hợp đồng của hàm hành vi trong Stream

Để một pipeline có thể được tối ưu hóa, phân chia và chạy đúng, các hàm truyền vào nhiều thao tác Stream thường được yêu cầu:

- **Non-interfering**: không sửa nguồn dữ liệu đang được Stream duyệt, trừ những trường hợp đặc biệt được tài liệu API cho phép.
- **Stateless**: kết quả xử lý phần tử không phụ thuộc trạng thái có thể thay đổi trong lúc pipeline chạy, nhất là trạng thái do các lời gọi khác thay đổi.
- **Tuân thủ hợp đồng của thao tác**: ví dụ accumulator/combiner của reduction phải kết hợp đúng; comparator phải so sánh nhất quán; predicate không được tự thay đổi nguồn.

Một hàm thuần (*pure function*) giúp dễ đáp ứng các điều kiện này:

```java
// Ánh xạ giá trị; không sửa biến ngoài hoặc đơn hàng nguồn.
Stream<Long> amounts = orders.stream()
        .map(order -> order.getAmountCents() * 2L);
```

Ở đây `orders` là nguồn hợp lệ và `getAmountCents()` trả `long`. Ví dụ chỉ minh họa hình dạng ánh xạ; nếu phép nhân có nguy cơ tràn, dùng `Math.multiplyExact` hoặc kiểu số phù hợp.

Trái lại:

```java
List<String> audit = new ArrayList<>();

Stream<String> ids = orders.stream()
        .map(order -> {
            audit.add(order.getId()); // Side effect ngoài pipeline.
            return order.getId();
        });
```

Khi mới tạo `ids`, pipeline **chưa nhất thiết chạy**, vì `map` là intermediate operation và lazy. Nếu terminal operation không cần gọi mapper với tất cả phần tử, `audit` không phản ánh toàn bộ đơn hàng. Nếu chuyển sang parallel, `ArrayList` chung còn có thể bị nhiều worker sửa đồng thời.

### 2.1. Side effect không bị cấm trong mọi tình huống

Tác dụng phụ là cần thiết khi ứng dụng **ghi kết quả ra ngoài**—gửi thông báo, ghi tệp, lưu database. Vấn đề là phải:

1. Đặt side effect ở **ranh giới được quản lý**, không giấu trong `map`/`filter` chỉ để “tiện gọi”.
2. Định nghĩa rõ **thứ tự**, **điều kiện thành công**, **phạm vi commit** và **cách xử lý retry**.
3. Không phụ thuộc vào số lần gọi hoặc thread chạy một callback khi API không cam kết.
4. Tách **chuẩn bị dữ liệu** khỏi **thực thi hành động bên ngoài** khi có thể.

Không nên cực đoan rằng mọi ứng dụng phải không có side effect; cần phân biệt **logic biến đổi thuần** và **I/O bắt buộc được kiểm soát**.

## 3. Vì sao peek và map không phải cơ chế audit đáng tin?

`peek` hữu ích cho quan sát/debug, nhưng không phải giao diện bảo đảm một hành động nghiệp vụ được gọi đúng một lần cho mọi bản ghi.

```java
List<String> values = Arrays.asList("A", "B", "C");

long count = values.stream()
        .peek(value -> System.out.println("Đã thấy " + value))
        .count();

System.out.println(count); // 3
```

Ở một số đường thực thi, `count()` có thể suy ra kích thước của nguồn và không cần duyệt qua từng phần tử. Tài liệu Stream cho phép tối ưu hóa bỏ việc gọi các callback trung gian nếu việc đó không thay đổi **kết quả được API bảo đảm**. Vì vậy, không được khẳng định ba dòng `Đã thấy ...` sẽ luôn được in.

Điều tương tự có thể xảy ra khi đặt side effect trong `map`:

```java
AtomicInteger processed = new AtomicInteger();

long result = values.stream()
        .map(value -> {
            processed.incrementAndGet();
            return value.toLowerCase();
        })
        .count();

// Không được khẳng định processed.get() luôn bằng result.
```

`AtomicInteger` giúp thao tác tăng **an toàn luồng** nếu callback thực sự chạy đồng thời; nó **không buộc runtime gọi mapper** trên mọi phần tử và không biến side effect thành một phép kiểm toán đầy đủ.

### 3.1. Sửa bằng cách diễn đạt kết quả trực tiếp

Nếu mục tiêu là **đếm**:

```java
long count = values.stream().count();
```

Nếu mục tiêu là **đếm số bản ghi theo loại**:

```java
Map<String, Long> counts = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.counting()));
```

Nếu mục tiêu là ghi **sự kiện audit bắt buộc**, hãy tổ chức một bước ghi có **cơ chế commit/idempotency** được định nghĩa riêng. Đừng dựa vào `peek` để quyết định một giao dịch đã được ghi nhận.

## 4. Short-circuit: một terminal operation có thể cố ý dừng sớm

Các thao tác như `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch` và những pipeline có `limit` có thể dừng mà không tiêu thụ hết nguồn:

```java
boolean hasError = messages.stream()
        .anyMatch(message -> message.startsWith("ERROR"));
```

Khi tìm được một lỗi, `anyMatch` không cần kiểm tra mọi thông điệp còn lại để trả `true`. Nếu predicate vừa kiểm tra vừa tăng biến đếm bên ngoài, số lần gọi predicate **không đại diện chắc chắn cho toàn bộ số thông điệp**.

### 4.1. Hai yêu cầu khác nhau

| Yêu cầu | Phép toán phù hợp | Có duyệt toàn bộ nguồn không? |
|---|---|---|
| Có **ít nhất một** lỗi hay không? | `anyMatch(isError)` | Có thể dừng tại lỗi đầu |
| Lỗi **đầu tiên theo thứ tự** là gì? | `filter(isError).findFirst()` | Có thể dừng sớm |
| Có **bao nhiêu** lỗi? | `filter(isError).count()` | Thông thường phải xét các phần tử cần thiết để đếm |
| Lấy **tối đa K** lỗi đầu tiên | `filter(isError).limit(K).collect(toList())` | Có thể dừng sau đủ K lỗi |
| Ghi **mọi** lỗi vào tệp | Terminal action/collector được thiết kế phù hợp | Phải hoàn thành toàn bộ nếu yêu cầu thành công đủ |

Không dùng `findFirst` chỉ vì chạy nhanh nếu yêu cầu là **đảm bảo tác động lên tất cả bản ghi**.

### 4.2. limit đặt ở đâu cũng là một quyết định nghiệp vụ

```java
// Tối đa 10 đơn hợp lệ đầu tiên.
orders.stream()
        .filter(Order::isValid)
        .limit(10);

// Chỉ xét 10 đơn đầu nguồn, rồi loại đơn không hợp lệ.
orders.stream()
        .limit(10)
        .filter(Order::isValid);
```

Hai pipeline **không tương đương** nếu dữ liệu có đơn không hợp lệ. Nếu trong `filter` có ghi database, cả số tác động lẫn phần dữ liệu được tác động có thể khác; vì vậy càng cần đưa side effect ra khỏi các bước biến đổi.

### 4.3. Không đếm số lần gọi lambda để suy ra kết quả

Với `parallelStream()`, cả số phần tử được duyệt trước khi dừng lẫn thứ tự gọi callback có thể khác giữa các lần chạy. Một số tác vụ đã bắt đầu có thể vẫn hoàn thành dù điều kiện dừng được tìm thấy. Chỉ sử dụng **giá trị trả về theo hợp đồng API**—không dùng biến counter phụ để khẳng định đã xử lý đúng K phần tử.

## 5. Ngoại lệ không làm hoàn tác side effect đã thực hiện

`Stream` không tự bọc mọi lambda trong một transaction. Ví dụ:

```java
List<String> sent = new ArrayList<>();

try {
    Stream.of("O1", "O2", "O3", "O4")
            .forEachOrdered(id -> {
                if ("O3".equals(id)) {
                    throw new IllegalStateException("Gửi O3 thất bại");
                }
                sent.add(id);
            });
} catch (IllegalStateException failure) {
    System.out.println(failure.getMessage());
}

System.out.println(sent); // [O1, O2] trong ví dụ tuần tự này.
```

`O1` và `O2` đã được thêm vào `sent`. Nếu `sent.add` đại diện cho một lệnh gửi thật, lệnh gửi có thể đã xảy ra và không tự bị hoàn tác khi `O3` ném ngoại lệ. `forEachOrdered` giúp xác định thứ tự hành động theo encounter order; nó **không cung cấp rollback**.

### 5.1. Tình trạng sau lỗi không phải một giá trị duy nhất

| Câu hỏi | Có bảo đảm chung không? |
|---|---|
| Những thay đổi bên ngoài trước khi gặp lỗi có tự mất đi không? | **Không** |
| Pipeline sẽ tạo một kết quả `collect` hoàn chỉnh sau ngoại lệ không? | **Không**, khi lỗi lan ra và terminal không hoàn tất |
| Có thể biết số phần tử đã tác động chỉ từ ngoại lệ không? | **Không** |
| Có bảo đảm callback đã được gọi đúng một lần cho từng phần tử không? | **Không** đối với mọi tổ hợp thao tác/đường tối ưu |
| Stream tự thực hiện bù trừ hoặc retry cho API bên ngoài không? | **Không** |
| Đóng Stream nguồn I/O có hoàn tác dữ liệu đã ghi ra đích không? | **Không** |

Vì thế, ứng dụng cần **một hợp đồng tiến độ/commit riêng** nếu tính đúng phụ thuộc vào việc xử lý đủ hoặc không trùng các phần tử.

### 5.2. Ngoại lệ trong map/filter/reduce/collect

Một mapper parse dữ liệu có thể ném `NumberFormatException`; predicate có thể ném lỗi khi gặp `null`; accumulator có thể ném `ArithmeticException` khi `Math.addExact` phát hiện tràn số. Trong các trường hợp này, nếu lỗi lan lên caller thì terminal operation không trả kết quả thông thường.

Nhưng phải tách hai loại trạng thái:

1. **Trạng thái trung gian do Stream/Collector quản lý**: thường không được công bố cho caller khi thu thập thất bại; không cần giả định nó được trả hoặc vẫn có thể sử dụng.
2. **Tác dụng phụ mà lambda đã đẩy ra ngoài**: ghi tệp, gửi mạng, sửa object chia sẻ. Những thay đổi này có thể đã tồn tại, ngay cả khi terminal không có giá trị trả về.

Vì vậy, “không thấy kết quả List/Map” không đồng nghĩa “chưa có bản ghi nào được gửi”.

## 6. Parallel Stream làm hoàn tất một phần khó dự đoán hơn

Trong parallel stream, các phần tử có thể được xử lý trên nhiều worker. Một lỗi ở một nhánh không tạo ra “điểm dừng đồng bộ tức thì” cho tất cả side effect đang chạy ở nhánh khác.

```java
List<String> sent =
        Collections.synchronizedList(new ArrayList<>());

try {
    Stream.of("O1", "O2", "O3", "O4", "O5", "O6")
            .parallel()
            .forEach(id -> {
                if ("O3".equals(id)) {
                    throw new IllegalStateException("O3 thất bại");
                }
                sent.add(id);
            });
} catch (IllegalStateException failure) {
    System.out.println("Bị lỗi: " + failure.getMessage());
}

// Chỉ kiểm tra minh họa, KHÔNG assert tập hoặc thứ tự cụ thể.
System.out.println(sent);
```

`Collections.synchronizedList` bảo vệ các thao tác riêng lẻ trên List khỏi data race, nhưng **không đảm bảo** một nghiệp vụ gồm nhiều bước là nguyên tử. Tập ID trong `sent` có thể phụ thuộc lịch thực thi; không được khẳng định chỉ `O1` và `O2` đã được gửi.

### 6.1. Thread-safe khác transactional

| Thuộc tính | Câu hỏi |
|---|---|
| **Thread-safe** | Khi nhiều thread gọi đồng thời, cấu trúc dữ liệu có tránh race/hỏng trạng thái không? |
| **Atomic operation** | Một phép cập nhật riêng lẻ có diễn ra nguyên tử theo hợp đồng của nó không? |
| **Transaction** | Một nhóm hành động có được commit/rollback như một đơn vị không? |
| **Idempotency** | Lặp lại cùng yêu cầu có tạo thêm tác động không? |
| **Exactly once effect** | Hệ thống bên ngoài có cơ chế bảo đảm hiệu ứng nghiệp vụ đúng một lần không? |

Một `ConcurrentHashMap` hoặc `AtomicInteger` có thể giúp tránh race đối với cấu trúc cụ thể. Nó **không** biến chuỗi `chargeCard(); sendEmail(); updateReport()` thành transaction và không giải quyết được việc retry sau lỗi mạng không rõ yêu cầu đã thành công hay chưa.

### 6.2. forEach và forEachOrdered

`forEach` trên Stream song song không cam kết thứ tự hành động. `forEachOrdered` tôn trọng encounter order nếu nguồn có thứ tự, và các action có quan hệ thực thi theo thứ tự đó; tuy nhiên các action không nhất thiết chạy trên cùng một thread.

**Điểm mấu chốt:** ngay cả `parallel().forEachOrdered(...)` cũng **không hoàn tác** các action đã thực hiện khi action sau ném lỗi. Nó bảo vệ ngữ nghĩa về thứ tự, **không** bảo vệ tính toàn vẹn của một loạt thao tác bên ngoài.

## 7. Mutable reduction hợp lệ khác shared mutable state

Java Stream cho phép trạng thái mutable **bên trong collector** để tích lũy dữ liệu:

```java
List<String> ids = orders.parallelStream()
        .map(Order::getId)
        .collect(Collectors.toList());
```

`Collectors.toList()` không công bố `CONCURRENT`, nhưng vẫn có thể chạy đúng trên parallel stream. Framework có thể tạo container riêng cho từng nhánh, sau đó gộp kết quả. Không vì `ArrayList` không thread-safe mà cho rằng mọi `collect(toList())` trên Stream song song đều sai.

Ngược lại:

```java
List<String> shared = new ArrayList<>();

orders.parallelStream()
        .map(Order::getId)
        .forEach(shared::add); // SAI: nhiều worker sửa một ArrayList chung.
```

Ở đoạn thứ hai, chính ứng dụng tạo shared mutable state ngoài pipeline rồi cập nhật bằng action. Lỗi là race và thiếu hợp đồng kết hợp; thêm `synchronizedList` có thể tránh race trên thao tác `add` nhưng **không** tạo ra thứ tự hay transaction theo yêu cầu nghiệp vụ.

### 7.1. Dùng Collector để tổng hợp số liệu, không dùng forEach để sửa Map chung

```java
Map<String, Long> countByRegion = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.counting()));
```

Nếu chỉ cần tổng theo khu vực, `groupingBy(..., counting())` diễn đạt chính xác yêu cầu hơn việc cho mỗi worker gọi `sharedMap.merge(...)`. Khi viết Collector tùy chỉnh, phải đảm bảo `supplier`, `accumulator`, `combiner`, `finisher` tuân thủ hợp đồng **đơn vị – kết hợp – tương đương** và không tự công bố `CONCURRENT` cho state không thread-safe.

### 7.2. Collector không tự bảo đảm commit bên ngoài

Một collector thực hiện `accumulator -> database.insert(row)` vẫn có side effect bên ngoài và có thể hoàn thành một phần khi lỗi. Dù collector tuân thủ hợp đồng giảm dữ liệu, **mỗi callback không phải một ranh giới commit toàn pipeline**. Tránh đặt lệnh ghi database trong accumulator/combiner nếu quy tắc retry, idempotency và rollback chưa được thiết kế.

## 8. Tách biến đổi thuần khỏi ranh giới side effect

Một kiến trúc thường dễ kiểm thử hơn:

```text
Nguồn
  |
  v
parse / validate / map / filter     [chỉ tính toán]
  |
  v
chuẩn bị lệnh hoặc kết quả          [chưa tác động bên ngoài]
  |
  v
commit có kiểm soát                [I/O, transaction, publish]
  |
  v
ghi nhận trạng thái và xử lý retry
```

### 8.1. Chuẩn bị trước, commit sau

Với dữ liệu đủ nhỏ để giữ trong bộ nhớ:

```java
List<String> commands = orders.stream()
        .map(order -> {
            if (!order.isValid()) {
                throw new IllegalArgumentException(
                        "Đơn không hợp lệ: " + order.getId());
            }
            return order.getId() + "\t" + order.getAmountCents();
        })
        .collect(Collectors.toList());

// Chỉ thực hiện sau khi phần chuẩn bị hoàn tất.
externalGateway.sendBatch(commands);
```

`externalGateway` là giao diện ứng dụng giả định. **Ưu điểm:** nếu `map` ném lỗi khi chuẩn bị, chưa gọi `sendBatch`. **Giới hạn:** `sendBatch` vẫn có thể ghi một phần rồi lỗi; chỉ có transaction hoặc giao thức batch/idempotency của gateway mới quyết định có atomic hay không.

Thêm nữa, `collect(toList())` giữ toàn bộ `commands`; không phù hợp với nguồn quá lớn. Khi đó cần **staging ra tệp/DB tạm, xử lý batch có giới hạn và cơ chế commit** phù hợp.

### 8.2. Nếu muốn xử lý mọi phần tử nhưng vẫn ghi lỗi

Không nên bắt mọi lỗi bằng `try/catch` rồi trả `null` để âm thầm bỏ qua:

```java
// Nguy hiểm nếu làm mất bản ghi và không có thống kê:
orders.stream()
        .map(order -> {
            try {
                return transform(order);
            } catch (RuntimeException failure) {
                return null;
            }
        })
        .filter(Objects::nonNull);
```

Nếu nghiệp vụ yêu cầu **tiếp tục sau dữ liệu lỗi**, hãy mô hình hóa kết quả parse:

```text
ParseResult
  - Success(value)
  - Failure(recordId, errorCode)
```

Sau đó thu thập hoặc ghi **riêng** kết quả hợp lệ và bản ghi lỗi (*dead-letter*) cùng với số đếm tổng. Không coi pipeline có thể tiếp tục là lý do bỏ mất dữ liệu mà không báo cáo.

## 9. Chương trình Java 8 hoàn chỉnh: nhận diện tác dụng phụ và kiểm tra kết quả

Ví dụ sau dùng một danh sách đơn hàng nhỏ để chứng minh:

1. Một terminal action ném lỗi **không xóa các tác động trước đó**.
2. Thu thập dữ liệu theo kiểu **biến đổi thuần** giúp kiểm tra đầu ra trước khi công bố.
3. Parallel `collect` có thể dùng để tổng hợp an toàn mà không sửa một Map chung ngoài pipeline.
4. Test nên kiểm tra **giá trị được API cam kết**, không khẳng định `peek` hoặc các action song song chạy theo lịch cụ thể.

Lưu thành `StreamSideEffectSafetyDemo.java` và chạy với **JDK 8 trở lên**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class StreamSideEffectSafetyDemo {

    static final class Order {
        private final String id;
        private final String region;
        private final long amountCents;

        Order(String id, String region, long amountCents) {
            this.id = Objects.requireNonNull(id, "id");
            this.region = Objects.requireNonNull(region, "region");
            this.amountCents = amountCents;
        }

        String getId() { return id; }
        String getRegion() { return region; }
        long getAmountCents() { return amountCents; }
        boolean isValid() { return amountCents >= 0; }
    }

    static String prepare(Order order) {
        if (!order.isValid()) {
            throw new IllegalArgumentException(
                    "Số tiền âm ở đơn " + order.getId());
        }
        return order.getId() + "=" + order.getAmountCents();
    }

    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("O1", "BAC", 100L),
                new Order("O2", "NAM", 200L),
                new Order("O3", "BAC", -1L),
                new Order("O4", "NAM", 300L)
        );

        // 1) Mô phỏng side effect trong terminal operation tuần tự.
        List<String> externallySent = new ArrayList<>();
        try {
            orders.stream().forEachOrdered(order -> {
                if (!order.isValid()) {
                    throw new IllegalStateException(
                            "Không gửi được " + order.getId());
                }
                externallySent.add(order.getId());
            });
            throw new AssertionError("Phải phát sinh lỗi ở O3");
        } catch (IllegalStateException expected) {
            System.out.println(expected.getMessage());
        }

        System.out.println(externallySent); // [O1, O2]
        check(externallySent.equals(
                Arrays.asList("O1", "O2")),
                "Side effect trước lỗi vẫn tồn tại");

        // 2) Chuẩn bị thuần: khi lỗi, List chưa được trả về.
        List<String> commands = null;
        try {
            commands = orders.stream()
                    .map(StreamSideEffectSafetyDemo::prepare)
                    .collect(Collectors.toList());
            throw new AssertionError("Phải từ chối đơn O3");
        } catch (IllegalArgumentException expected) {
            System.out.println(expected.getMessage());
        }
        check(commands == null,
                "Không công bố List mới khi validation thất bại");

        // 3) Khi sửa dữ liệu đầu vào, có thể thu thập toàn bộ.
        List<Order> validOrders = Arrays.asList(
                new Order("O1", "BAC", 100L),
                new Order("O2", "NAM", 200L),
                new Order("O3", "BAC", 250L),
                new Order("O4", "NAM", 300L)
        );

        List<String> prepared = validOrders.stream()
                .map(StreamSideEffectSafetyDemo::prepare)
                .collect(Collectors.toList());

        check(prepared.equals(Arrays.asList(
                "O1=100", "O2=200", "O3=250", "O4=300")),
                "Chuẩn bị đủ bốn lệnh");
        System.out.println(prepared);

        // 4) Mutable reduction do Stream/Collector quản lý.
        Map<String, Long> grouped = validOrders.parallelStream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.counting()));
        check(grouped.get("BAC") == 2L
                && grouped.get("NAM") == 2L,
                "groupingBy chạy song song đúng số đếm");

        // 5) Kết quả List của collector không cần sửa
        // bất kỳ ArrayList chung từ nhiều thread.
        List<String> ids = validOrders.parallelStream()
                .map(Order::getId)
                .collect(Collectors.toList());
        check(ids.equals(Arrays.asList(
                "O1", "O2", "O3", "O4")),
                "toList giữ encounter order của List nguồn");

        // 6) Khi chỉ cần chỉ số, đừng giấu counter trong peek.
        long paidLikeCount = validOrders.stream()
                .filter(order -> order.getAmountCents() > 0)
                .count();
        check(paidLikeCount == 4L, "Đếm trực tiếp");

        System.out.println("PASS: semantic checks");
    }
}
```

### 9.1. Điều gì được kiểm tra, điều gì không?

Chương trình cố ý dùng `forEachOrdered` tuần tự khi mô phỏng lỗi `O3`, nên trong ví dụ này `externallySent` chứa đúng `O1, O2`. Đây là **kiểm thử hành vi của đoạn code cụ thể**, không phải bằng chứng rằng mọi parallel `forEach` khi lỗi đều gửi đúng hai đơn đầu.

Trong đoạn chuẩn bị, `commands` chỉ được gán sau khi `collect` trả về thành công. Khi `prepare` ném lỗi, biến `commands` vẫn là `null`; tuy nhiên **không có đảm bảo chung rằng mọi chương trình đặt side effect bên trong map sẽ không có tác động**. Lợi ích đến từ việc `prepare` là hàm thuần và chưa hề gọi hệ thống bên ngoài.

### 9.2. Test với parallel Stream

Khi kiểm tra kết quả `groupingBy` song song, chương trình so **giá trị theo khóa** chứ không so thứ tự in của `HashMap`. Tương tự, `collect(toList())` trên nguồn List có encounter order giữ thứ tự phần tử theo hợp đồng; không suy ra các mapper đã được thực thi lần lượt trên một thread.

## 10. Ví dụ Java 8 hoàn chỉnh: ghi tệp tạm rồi công bố khi thành công

Đối với file export lớn, tạo toàn bộ `List` trước khi ghi có thể quá tốn RAM. Một cách thiết kế an toàn hơn cho **một tệp đầu ra mới**:

1. Mở nguồn bằng `Files.lines` trong `try-with-resources`.
2. Ghi từng dòng đã chuẩn hóa vào một **tệp tạm trong cùng thư mục đích**.
3. Nếu parse hoặc ghi lỗi, **đóng tài nguyên rồi xóa tệp tạm**, không công bố tệp kết quả.
4. Chỉ sau khi toàn bộ việc chuẩn bị thành công, **move tệp tạm thành tên kết quả** bằng `ATOMIC_MOVE` nếu hệ thống tệp hỗ trợ.

Phương án này **giảm hiển thị kết quả chưa hoàn chỉnh**, nhưng không phải transaction đa tài nguyên và không đảm bảo tự động giải quyết mọi sự cố như mất điện, lỗi ổ đĩa, hoặc ghi cùng lúc ở nhiều hệ thống. Ví dụ chỉ công bố **tệp đích chưa tồn tại**, không thực hiện giao thức thay thế tệp có sẵn.

Lưu thành `StreamStagedFileDemo.java`; code tự tạo dữ liệu mẫu nên chạy độc lập bằng **JDK 8 trở lên**:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

public class StreamStagedFileDemo {

    // Dữ liệu ví dụ: id;amountCents (không có header).
    static String normalize(String line) {
        String[] columns = line.split(";", -1);
        if (columns.length != 2
                || columns[0].trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "Sai định dạng: " + line);
        }
        long cents = Long.parseLong(columns[1].trim());
        if (cents < 0) {
            throw new IllegalArgumentException(
                    "Số tiền âm: " + line);
        }
        return columns[0].trim() + "\t" + cents;
    }

    // Chỉ dùng cho tệp đích mới, chưa tồn tại.
    static void exportToNewFile(Path input, Path target)
            throws IOException {
        Path absoluteTarget = target.toAbsolutePath();
        Path parent = absoluteTarget.getParent();

        if (Files.exists(absoluteTarget)) {
            throw new IllegalArgumentException(
                    "Tệp đích phải chưa tồn tại");
        }

        Path staging = Files.createTempFile(
                parent, "stream-stage-", ".tmp");
        boolean published = false;

        try {
            try (Stream<String> lines =
                         Files.lines(input, StandardCharsets.UTF_8);
                 BufferedWriter writer =
                         Files.newBufferedWriter(
                                 staging, StandardCharsets.UTF_8)) {

                lines.map(StreamStagedFileDemo::normalize)
                        .forEachOrdered(value -> {
                            try {
                                writer.write(value);
                                writer.newLine();
                            } catch (IOException cause) {
                                throw new UncheckedIOException(cause);
                            }
                        });
            }

            // Nếu không được hỗ trợ, để lỗi lan lên caller:
            // KHÔNG tự fallback sang move không nguyên tử.
            Files.move(staging, absoluteTarget,
                    StandardCopyOption.ATOMIC_MOVE);
            published = true;
        } finally {
            if (!published) {
                Files.deleteIfExists(staging);
            }
        }
    }

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory =
                Files.createTempDirectory("stream-safety-");
        Path valid = directory.resolve("valid.txt");
        Path invalid = directory.resolve("invalid.txt");
        Path published = directory.resolve("published.txt");
        Path rejected = directory.resolve("rejected.txt");

        try {
            Files.write(valid,
                    Arrays.asList("O1;100", "O2;200", "O3;300"),
                    StandardCharsets.UTF_8);
            Files.write(invalid,
                    Arrays.asList("O1;100", "O2;200", "O3;BAD"),
                    StandardCharsets.UTF_8);

            exportToNewFile(valid, published);
            List<String> exported = Files.readAllLines(
                    published, StandardCharsets.UTF_8);
            check(exported.equals(Arrays.asList(
                    "O1\t100", "O2\t200", "O3\t300")),
                    "Tệp hợp lệ phải chứa toàn bộ dữ liệu");
            System.out.println(exported);

            try {
                exportToNewFile(invalid, rejected);
                throw new AssertionError("Phải ném lỗi parse");
            } catch (NumberFormatException expected) {
                check(!Files.exists(rejected),
                        "Không công bố tệp kết quả sai");
                System.out.println(
                        "Đã từ chối tệp lỗi; không có rejected.txt");
            }
        } catch (AtomicMoveNotSupportedException unsupported) {
            System.out.println(
                    "Filesystem không hỗ trợ ATOMIC_MOVE; "
                    + "không công bố tệp theo cơ chế này");
        } finally {
            Files.deleteIfExists(valid);
            Files.deleteIfExists(invalid);
            Files.deleteIfExists(published);
            Files.deleteIfExists(rejected);
            Files.deleteIfExists(directory);
        }
    }
}
```

### 10.1. Điều ví dụ thực sự bảo vệ

Khi đọc `invalid.txt`, hai dòng đầu có thể đã được ghi vào **tệp staging**, rồi `NumberFormatException` ở dòng ba. Khối `try-with-resources` đóng reader/writer, sau đó `finally` xóa staging. Caller **không nhìn thấy tệp `rejected.txt` như một kết quả thành công**.

Nếu hệ thống tệp không hỗ trợ `ATOMIC_MOVE`, code **báo rõ lỗi** thay vì âm thầm chuyển sang copy/move không nguyên tử. Việc đổi tên tệp nguyên tử chỉ áp dụng trong phạm vi và những đảm bảo của filesystem; nó **không** đồng nghĩa dữ liệu đã được đồng bộ bền vững xuống thiết bị lưu trữ trong mọi trường hợp.

### 10.2. Giới hạn và tình huống cần xử lý ngoài phạm vi demo

- `Files.exists` rồi `Files.move` không giải quyết hoàn toàn race khi **nhiều tiến trình cùng chọn một tên đích**. Việc công bố tệp đã tồn tại hoặc ghi đè yêu cầu giao thức tương tranh phù hợp.
- Nếu có lỗi khi xóa staging, lỗi dọn dẹp cũng cần được quan sát; khi thiết kế production nên ghi nhận cả lỗi chính và lỗi cleanup.
- Với nhiều tệp đầu ra, không thể dùng một phép rename để tự tạo **transaction nguyên tử cho tất cả tệp**.
- Nếu vừa ghi tệp vừa gửi email/database trong cùng pipeline, thao tác move không rollback những side effect ở hệ thống khác.
- `Files.lines` vẫn có thể materialize một dòng rất dài; dùng parser/reader có giới hạn đầu vào nếu cần hard cap bộ nhớ.
- Demo là ví dụ định dạng `id;amountCents` đơn giản, không phải parser CSV có quoting/escaping.

**Bộ nhớ:** phương án staging ghi từng dòng, không giữ một `List` toàn bộ dữ liệu. Bộ nhớ chủ yếu dành cho dòng đang xử lý, buffer I/O và trạng thái pipeline; kích thước **tệp staging trên đĩa** vẫn tăng theo dữ liệu xuất ra. Phải kiểm soát cả dung lượng đĩa, quota và lỗi ghi đầy ổ.

## 11. Retry, idempotency và transaction ở hệ thống bên ngoài

### 11.1. Cần phân biệt lỗi trước và sau commit

| Trường hợp | Điều đã biết | Quyết định retry |
|---|---|---|
| Validation thất bại trước khi gọi API | Chưa gọi side effect | Có thể sửa dữ liệu rồi chạy lại |
| API trả lỗi rõ ràng trước khi thực hiện tác động | Theo hợp đồng cụ thể của API | Retry theo chính sách API |
| Timeout sau khi gửi yêu cầu mạng | **Không chắc** server đã commit hay chưa | Cần idempotency key/trạng thái truy vấn |
| Đã commit một batch rồi lỗi ở batch sau | Batch trước đã có hiệu ứng | Retry có phạm vi, tránh thực hiện trùng |
| Một Stream song song ném lỗi | Các action khác có thể đã chạy | Không dựa vào encounter order để đoán phạm vi thành công |

**Không thể đạt “exactly once” cho một side effect bên ngoài chỉ bằng cách đổi `map` thành `forEach` hoặc thêm `synchronized`.** Bảo đảm phụ thuộc vào giao thức bên ngoài, lưu trạng thái commit, giao dịch và chiến lược retry.

### 11.2. Idempotency key theo nghiệp vụ

Ví dụ gửi yêu cầu tạo hóa đơn:

```text
operation = "CREATE_INVOICE"
orderId   = "O123"
key       = "CREATE_INVOICE:O123"
```

Ứng dụng có thể truyền key cho một gateway **thực sự hỗ trợ idempotency**. Khi gửi lại đúng yêu cầu với cùng key, gateway theo hợp đồng của nó có thể trả kết quả cũ thay vì tạo hóa đơn thứ hai.

Điều kiện đi kèm:

- Key phải ổn định giữa các lần retry của **cùng tác vụ nghiệp vụ**.
- Không tái sử dụng key cho **hai tác vụ khác nhau**.
- Nếu payload thay đổi nhưng key giữ nguyên, gateway phải có chính sách xử lý xung đột.
- Thời hạn lưu trạng thái idempotency và retry window phải phù hợp.

Đây là một **thiết kế ở tầng hệ thống**, không phải tính năng được Java Stream API tự cung cấp.

### 11.3. Transaction và outbox

Khi dữ liệu phải được lưu vào database, có thể:

1. Parse/validate các record trước.
2. Mở transaction ở tầng persistence.
3. Ghi các thay đổi của **một đơn vị công việc đã chọn**.
4. Commit thành công hoặc rollback nếu database và loại transaction hỗ trợ.

Với nhu cầu đồng thời **ghi database và phát thông điệp**, mô hình *transactional outbox* có thể ghi thay đổi nghiệp vụ và bản ghi outbox trong **cùng database transaction**. Một worker khác phát thông điệp từ outbox với cơ chế retry/dedup. Cách này giúp tránh tình huống đã commit database nhưng mất thông điệp, tuy nhiên consumer vẫn cần idempotency vì việc phát lại có thể xảy ra.

Không khẳng định một Stream duy nhất thực hiện cả hai hệ thống đã tạo được transaction phân tán.

## 12. Theo dõi tiến độ và phục hồi sau hoàn tất một phần

Với tệp lớn, không thể luôn giữ toàn bộ record trong RAM rồi commit một lần. Khi xử lý theo lô, cần **đơn vị checkpoint** rõ ràng:

```text
Batch 1: chuẩn bị -> commit -> checkpoint 1
Batch 2: chuẩn bị -> commit -> checkpoint 2
Batch 3: chuẩn bị -> lỗi
Khởi chạy lại: bắt đầu từ vị trí sau checkpoint 2
```

Checkpoint chỉ có giá trị nếu nó **liên kết đúng với kết quả đã commit**. Nếu ghi checkpoint trước rồi ghi kết quả sau, lỗi giữa hai bước có thể làm **mất** bản ghi. Nếu ghi kết quả trước rồi checkpoint sau, lỗi giữa hai bước có thể làm **lặp** tác động khi retry. Cần transaction cùng hệ thống hoặc cơ chế idempotent/dedupe để xử lý khoảng trống này.

### 12.1. Chọn khóa tiến độ bền vững

- Với nguồn database: khóa tăng dần/cursor có thể phù hợp hơn chỉ số trang offset.
- Với message broker: offset, partition và hợp đồng commit offset của broker.
- Với tệp: byte offset hoặc số dòng chỉ an toàn khi nguồn **không thay đổi** và có cách định danh phiên bản/checksum tệp.
- Với API có phân trang: cursor token cần được lưu cùng danh tính truy vấn và phiên bản dữ liệu, nếu API có các yêu cầu đó.

Một biến `AtomicLong processed` trong JVM chỉ là **số đếm tại runtime**, không đủ làm checkpoint tin cậy khi tiến trình chết hoặc khi tác động bên ngoài chưa được xác nhận.

### 12.2. Batch có giới hạn nhưng đừng quên lỗi giữa batch

Nếu xử lý `K` dòng mỗi batch, bộ nhớ có thể bị ràng buộc theo `K` thay vì `n`. Tuy nhiên, **tính nguyên tử thường chỉ có thể áp dụng ở ranh giới từng batch**, không phải toàn bộ tệp trừ khi storage hỗ trợ transaction đủ lớn.

Với batch gửi bất đồng bộ, cần giới hạn **cả kích thước batch lẫn số batch đang chờ**. Nếu hàng đợi không giới hạn, dù mỗi batch nhỏ, tổng bộ nhớ vẫn có thể tăng không giới hạn và lỗi có thể để lại rất nhiều batch ở trạng thái không rõ kết quả.

## 13. Tài nguyên I/O: đóng tài nguyên không phải rollback

`Files.lines` và các Stream nguồn I/O có thể cần đóng khi xử lý xong hoặc có lỗi:

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long valid = lines
            .map(String::trim)
            .filter(line -> !line.isEmpty())
            .count();
}
```

`try-with-resources` bảo đảm gọi `close` khi rời khối, kể cả khi một bước trong pipeline ném ngoại lệ. Nhưng **đóng reader không xóa dữ liệu đã ghi**, **đóng writer không bảo đảm transaction cho tệp**, và **đóng HTTP client không hoàn tác yêu cầu đã được server xử lý**.

### 13.1. Stream một lần và vòng đời nguồn

- Một đối tượng Stream chỉ được tiêu thụ **một lần**; không gọi terminal operation thứ hai sau khi đã tiêu thụ.
- Không trả Stream được tạo trong khối `try` đã đóng mà mong caller tiếp tục đọc.
- Nếu một API trả Stream còn mở, phải có hợp đồng rõ ràng về **ai đóng** và **khi nào**.
- `onClose` có thể đăng ký hành động đóng tài nguyên, nhưng việc tiêu thụ bằng `collect` hoặc `count` **không tự đóng mọi Stream nguồn**.
- Với nguồn I/O, một ngoại lệ lúc duyệt có thể được bọc trong `UncheckedIOException`; ghi nhận nguyên nhân gốc và vẫn giải phóng tài nguyên.

### 13.2. Side effect trong flatMap và Gatherer

`flatMap` mở Stream con có thể gắn tài nguyên; Stream API có hợp đồng đóng các Stream con khi chúng đã được làm phẳng. Tuy nhiên, **mỗi tài nguyên mở bên ngoài hoặc được quản lý thủ công** vẫn cần sở hữu rõ ràng.

Với Stream Gatherers từ Java 24, integrator có thể giữ state và có thể phát đầu ra theo quy tắc riêng, nhưng Gatherer cũng **không phải transaction manager**. Dừng sớm, finisher hay tích hợp song song **không tạo rollback** cho các tác động đã ghi ra ngoài. Không đặt thao tác thanh toán hoặc gửi thông điệp trong integrator với giả định toàn bộ pipeline sẽ hoàn tất hoặc tự bù trừ khi lỗi.

## 14. Kiểm thử đúng ngữ nghĩa, không kiểm thử lịch chạy

Một bộ kiểm thử an toàn cần tách:

| Loại test | Điều cần xác nhận |
|---|---|
| **Pure transform** | Dữ liệu đúng, null và dữ liệu lỗi được xử lý theo hợp đồng |
| **Short-circuit** | Giá trị trả về đúng; không assert số lần gọi `peek` |
| **Sequential failure** | Side effect trước lỗi vẫn tồn tại nếu không có rollback được thiết kế |
| **Parallel failure** | Không race/hỏng trạng thái; không assert tập phần tử hoàn tất cố định |
| **Collector** | Kết quả tuần tự và song song tương đương, combiner đúng hợp đồng |
| **File staging** | Parse lỗi không tạo tệp đích, staging được dọn; không dựa vào hỗ trợ ATOMIC_MOVE ở mọi filesystem |
| **Retry/idempotency** | Gửi lại cùng key không tạo thêm tác động **theo hợp đồng gateway giả lập** |
| **Checkpoint** | Lỗi trước/sau commit không làm mất hoặc nhân đôi tác động ngoài chính sách đã định |
| **I/O** | Stream, reader, writer được đóng cả khi thành công và có lỗi |

### 14.1. Bất biến nên kiểm tra

Với báo cáo chỉ cần số liệu, ưu tiên kiểm tra:

```text
tổng count theo nhóm == số bản ghi hợp lệ
tổng tiền theo nhóm == tổng tiền toàn bộ
kết quả tuần tự tương đương kết quả song song
không xuất hiện bản ghi đã bị chính sách validation từ chối
```

Với hệ thống xuất dữ liệu, thêm:

```text
không công bố tên tệp đích khi bước chuẩn bị thất bại
chỉ chuyển checkpoint sau khi commit phù hợp
không gửi trùng khi retry cùng idempotency key
không để lộ tệp staging chưa hoàn tất như báo cáo cuối
```

Những bất biến này sát với nghiệp vụ hơn các kiểm thử kiểu “`peek` được gọi đúng n lần” hoặc “thread A xử lý O1 trước thread B”.

## 15. Các nhầm lẫn và lỗi phổ biến

| Nhận định hoặc cách làm | Vì sao không an toàn | Thay bằng |
|---|---|---|
| “`peek` luôn chạy một lần trên mỗi phần tử.” | Tối ưu hóa/short-circuit có thể bỏ hoặc dừng callback | Dùng kết quả Stream được API bảo đảm |
| “Đặt `db.insert` trong `map` để vừa biến đổi vừa lưu.” | Giấu side effect, khó xác định commit/retry | Tách biến đổi và bước ghi có hợp đồng |
| “`forEach` ném lỗi thì mọi bản ghi trước đó rollback.” | Stream không có transaction | Transaction/staging hoặc bù trừ |
| “`forEachOrdered` có rollback vì giữ thứ tự.” | Chỉ ràng buộc thứ tự hành động | Thiết kế ranh giới commit riêng |
| “`AtomicInteger` giải quyết exactly-once.” | Chỉ bảo vệ thao tác tăng bộ đếm | Idempotency/transaction/checkpoint |
| “SynchronizedList đồng nghĩa kết quả nguyên tử.” | Có thể cập nhật một phần trước lỗi | Không dùng shared state cho nghiệp vụ cần atomic |
| “Dùng `parallel()` luôn xử lý xong mọi phần tử trước khi ném lỗi.” | Tác vụ có thể còn đang hoạt động; lịch không định trước | Không suy trạng thái từ thứ tự |
| “`Collectors.toList()` sai trên parallel stream.” | Framework có thể có container cục bộ và combiner | Dùng collector đúng hợp đồng |
| “Tự viết Collector.CONCURRENT cho HashMap sẽ nhanh hơn.” | `CONCURRENT` là cam kết thread-safety, không tạo bảo vệ | Chỉ công bố khi accumulator thật sự an toàn |
| “Không có kết quả `collect` nghĩa là chưa gửi bản ghi.” | Side effect ngoài pipeline vẫn có thể tồn tại | Theo dõi commit/ack ở hệ thống đích |
| “Retry cả tệp sau timeout là an toàn.” | Có thể đã commit một phần | Idempotency key hoặc checkpoint |
| “try-with-resources sẽ hoàn tác file đã ghi.” | Chỉ đóng tài nguyên | Staging + publish/transaction phù hợp |
| “Ghi ra tệp tạm rồi move là transaction đa hệ thống.” | Chỉ xử lý phạm vi một tệp và filesystem hỗ trợ | Dùng giao thức giao dịch phù hợp hệ thống |
| “Chỉ cần bắt lỗi rồi trả null.” | Có thể mất bản ghi không được thống kê | ParseResult thành công/thất bại rõ |
| “Count biến phụ chứng minh mọi callback đã chạy.” | Lazy/short-circuit/elision và song song | Kiểm tra trực tiếp kết quả/đơn vị commit |

## 16. Bài tập thực hành có đáp án

### Bài 1. Nhận diện side effect bị bỏ qua

**Đề bài:** Vì sao không dùng `peek(audit::record)` trước `count()` để ghi audit bắt buộc?

**Đáp án:** `peek` là intermediate operation; `count()` có thể biết kích thước mà không cần duyệt callback, hoặc pipeline có thể dừng sớm trong những tình huống khác. Kết quả đếm được bảo đảm không đồng nghĩa side effect của `peek` đã chạy đúng n lần. Thiết kế bước audit ở ranh giới ghi có hợp đồng commit/idempotency.

### Bài 2. forEachOrdered ném lỗi

**Đề bài:** `Stream.of("A","B","C").forEachOrdered(...)` ghi A, ghi B, rồi ném ngoại lệ khi gặp C. Những gì đã ghi có tự mất không?

**Đáp án:** Không. `forEachOrdered` bảo toàn thứ tự action theo encounter order, nhưng không rollback A và B. Nếu muốn đầu ra có tính toàn vẹn, dùng một transaction thích hợp hoặc ghi vào tệp staging rồi chỉ công bố sau khi hoàn tất.

### Bài 3. anyMatch có duyệt hết?

**Đề bài:** `List.of("ERROR","OK","OK").stream().anyMatch(s -> s.startsWith("ERROR"))` có bắt buộc gọi predicate trên cả ba phần tử không?

**Đáp án:** Không; `anyMatch` có thể dừng khi gặp phần tử thỏa đầu. `List.of` chỉ có từ Java 9, nhưng ngữ nghĩa ngắn mạch của `anyMatch` có từ Java 8. Không dùng số lần gọi predicate để tính “đã xử lý bao nhiêu bản ghi”.

### Bài 4. Đếm an toàn trên parallel stream

**Đề bài:** Dùng `parallelStream().forEach(o -> count[0]++)` với mảng `long[1]`, có bảo đảm đếm đúng không? `AtomicLong` có giải quyết cả tính nghiệp vụ không?

**Đáp án:** Mảng chung bị data race và có thể mất cập nhật. `AtomicLong` tránh race của phép tăng nhưng không bảo đảm mọi callback được gọi khi pipeline dừng sớm/lỗi, và không thay transaction. Nếu chỉ cần số lượng, dùng `count()` hoặc `Collectors.counting()`.

### Bài 5. Kết quả collect khi mapper ném lỗi

**Đề bài:** Trong `stream.map(parse).collect(toList())`, parser lỗi ở một phần tử. Caller có thể lấy một `List` kết quả hoàn chỉnh từ terminal operation đó không?

**Đáp án:** Không, nếu lỗi lan ra; `collect` không trả kết quả thông thường. Nếu parser là hàm thuần, không có side effect bên ngoài cần rollback. Nếu parser đã gọi API/gửi log nghiệp vụ, các tác động trước lỗi có thể vẫn tồn tại.

### Bài 6. Retry sau timeout HTTP

**Đề bài:** Client gọi `POST /invoice` rồi timeout. Có nên giả định server chưa tạo hóa đơn và gọi lại không?

**Đáp án:** Không. Timeout không cho biết server đã commit hay chưa. Cần idempotency key, khả năng truy vấn trạng thái theo khóa nghiệp vụ hoặc giao thức retry của server. Stream API không tự biết trạng thái giao dịch bên ngoài.

### Bài 7. Ghi tệp lớn có cần giữ tất cả?

**Đề bài:** Muốn chuẩn hóa 5 triệu dòng rồi công bố một tệp báo cáo; `collect(toList())` có bắt buộc không?

**Đáp án:** Không. Có thể đọc bằng `Files.lines`, ghi dần vào tệp staging bằng `BufferedWriter`, đóng thành công rồi công bố theo giao thức tệp. Bộ nhớ không cần giữ toàn bộ năm triệu dòng, nhưng phải kiểm soát độ dài một dòng, dung lượng đĩa và xử lý lỗi trước lúc publish.

### Bài 8. Side effect với Gatherer

**Đề bài:** Java 24 Gatherer có integrator gửi email cho mỗi phần tử. Nếu downstream dùng `limit(2)` hoặc một phần tử làm lỗi, có thể khẳng định tất cả email đã được gửi đúng một lần không?

**Đáp án:** Không. Gatherer có thể dừng sớm theo downstream; lỗi không rollback email đã gửi. Các phép biến đổi cần giữ state riêng, còn gửi email phải có giao thức idempotency/commit phù hợp, không gắn tính đúng vào số lần gọi integrator.

### Bài 9. Atomic move và sự cố hệ thống

**Đề bài:** Có thể dùng `Files.move(temp, target, ATOMIC_MOVE)` và khẳng định cả tệp cùng cơ sở dữ liệu đã commit nguyên tử không?

**Đáp án:** Không. Atomic move chỉ có các đảm bảo trong phạm vi operation và filesystem hỗ trợ; nó không phối hợp transaction với database. Nếu hệ thống không hỗ trợ atomic move, ứng dụng phải quyết định báo lỗi hoặc dùng giao thức khác—không âm thầm tự nhận một phép move thường là nguyên tử.

### Bài 10. Thiết kế checkpoint

**Đề bài:** Sau khi ghi thành công batch thứ hai, chương trình chết trước khi ghi checkpoint. Nếu chạy lại từ checkpoint cũ, điều gì có thể xảy ra?

**Đáp án:** Batch thứ hai có thể được thực hiện lại. Cần idempotent writes/dedup hoặc transaction có thể commit trạng thái tiến độ và dữ liệu cùng nhau khi khả thi. Ghi checkpoint trước khi commit cũng sai theo hướng khác: có thể bỏ mất dữ liệu.

## 17. Checklist an toàn trước khi triển khai Stream

1. **Đã xác định rõ side effect chưa?** Ghi tệp, database, HTTP, email, counter hay sửa một collection ngoài pipeline?
2. **Các mapper/predicate có stateless và non-interfering không?** Có sửa nguồn hoặc dựa vào biến chung không?
3. **Có phụ thuộc số lần gọi `peek`/`map` để kiểm toán không?** Nếu có, hãy thiết kế lại.
4. **Có thao tác ngắn mạch không?** `limit`, `findFirst`, `findAny`, `anyMatch` có thể dừng trước khi duyệt hết.
5. **Nguồn có encounter order không?** Có cần giữ thứ tự các action hay chỉ cần kết quả tập hợp?
6. **Nếu một phần tử ném lỗi, các tác động trước đó đi đâu?** Có commit, rollback hoặc bù trừ phù hợp không?
7. **Có parallel stream không?** Đã tránh state mutable chung và không suy ra lịch xử lý cụ thể chưa?
8. **Có dùng Collector đúng hợp đồng không?** Supplier/accumulator/combiner và characteristics đã chính xác chưa?
9. **Có gateway bên ngoài không?** Đã có idempotency key, timeout policy, acknowledgement và retry window chưa?
10. **Có batch/checkpoint không?** Khi crash giữa commit và checkpoint có thể mất/trùng dữ liệu không?
11. **Có ghi file không?** Có đóng nguồn/đích, staging, publish và xử lý dọn dẹp khi lỗi chưa?
12. **Có dữ liệu lỗi không?** Fail-fast hay ghi nhận lỗi rõ ràng; có đang lọc bỏ bản ghi âm thầm không?
13. **Có giới hạn tài nguyên không?** Bộ nhớ tạm, số batch chờ, độ dài dòng, kích thước kết quả và số file mở?
14. **Bộ test có kiểm tra lỗi giữa chừng không?** Đừng chỉ test đường thành công.
15. **Đã tách “kết quả đúng” khỏi “tác dụng phụ đã commit” chưa?** Hai khái niệm phải được kiểm tra riêng.

**Kết luận:** Java Stream API là công cụ diễn đạt phép biến đổi và tổng hợp, **không** phải bộ quản lý giao dịch hay hệ thống tự bảo đảm exactly-once. Side effect giấu trong `map`/`peek` dễ bị bỏ qua, dừng sớm hoặc chạy không theo thứ tự kỳ vọng; side effect trong terminal action có thể **hoàn tất một phần** trước khi ngoại lệ lan ra; parallel stream càng khiến phạm vi đó khó suy đoán. Hãy dùng hàm biến đổi thuần, collector đúng hợp đồng, ranh giới ghi được kiểm soát, tài nguyên được đóng, staging/transaction và idempotency/checkpoint khi cần. Khi đó pipeline vẫn hưởng lợi từ cách viết khai báo mà không đánh đổi tính đúng và khả năng phục hồi sau lỗi.
