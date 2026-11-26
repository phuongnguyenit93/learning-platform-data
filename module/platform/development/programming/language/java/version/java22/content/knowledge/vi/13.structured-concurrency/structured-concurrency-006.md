# Lan truyền lỗi, hủy tác vụ còn lại và xử lý interruption đúng cách

## Phạm vi và phiên bản sử dụng

Bài học thuộc chương **Đồng thời có cấu trúc** của module **JAVA_VERSION_JAVA22**, dành cho việc học những tính năng có mặt ở Java 22 và còn hữu ích trong Java hiện đại. Nội dung tập trung vào ba trách nhiệm đi cùng nhau: đưa lỗi của tác vụ con về tác vụ cha, hủy công việc không còn cần thiết và phản hồi đúng yêu cầu ngắt luồng.

Structured Concurrency đã là API preview trong Java 22; Java 22 không phải lần đầu API xuất hiện. Cơ chế quản lý một nhóm tác vụ có vòng đời giới hạn vẫn còn áp dụng, nhưng API đã thay đổi qua các vòng preview. Có thể đối chiếu bối cảnh ở [StructuredTaskScope của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

**Mốc đối chiếu của bài là ngày 25/11/2026. Các ví dụ dùng JDK 27**, nơi Structured Concurrency vẫn ở lần preview thứ bảy. Bài dùng `StructuredTaskScope.open()` và cơ chế exception của Java 27, không dùng những biến thể API preview cũ làm mẫu triển khai mới. Trạng thái này được xác nhận trong [các thay đổi của JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html).

Trừ khi nói rõ khác đi, mọi diễn giải dưới đây sử dụng chính sách mặc định của `StructuredTaskScope.open()`: **cần tất cả tác vụ thành công; một tác vụ thất bại thì hủy phần còn lại**.

## 1. Phân biệt lỗi, hủy tác vụ và interruption

Giả sử một phương thức tạo thông tin chào hàng cần đồng thời lấy giá và kiểm tra tồn kho. Nếu giá không đọc được thì kết quả tổng hợp không thể tạo thành công; tác vụ kiểm tra tồn kho đang chờ cũng không còn cần thiết.

Có ba sự kiện khác nhau trong tình huống này:

| Sự kiện | Ý nghĩa |
| --- | --- |
| Tác vụ lấy giá thất bại | Lời gọi của tác vụ con kết thúc bằng exception hoặc error. |
| Scope bị hủy | Nhóm công việc được yêu cầu ngừng những tác vụ chưa hoàn tất. |
| Luồng nhận interruption | Luồng được gửi tín hiệu hợp tác để dừng hoặc hủy hoạt động hiện tại. |

Một tác vụ con thất bại không có nghĩa JVM đã ném cùng exception đó trực tiếp vào luồng cha. Với chính sách mặc định của JDK 27, cha nhận `ExecutionException` khi gọi `join()`, còn lỗi của tác vụ con nằm trong `getCause()`.

Tương tự, yêu cầu hủy không có nghĩa mọi luồng đã dừng ngay. Scope gửi interruption tới các luồng đang thực thi tác vụ chưa hoàn tất; mã trong những tác vụ đó phải phản hồi tín hiệu. Nếu chúng bỏ qua interruption, quá trình đóng scope vẫn phải chờ.

Hợp đồng mặc định và quan hệ giữa hủy, `join()` và `close()` được mô tả trong [StructuredTaskScope của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

## 2. Luồng lan truyền lỗi với chính sách cần mọi tác vụ thành công

Ở đường thành công, cha fork các tác vụ, gọi `join()`, rồi đọc kết quả của những tác vụ đã thành công. Ở đường lỗi, diễn tiến điển hình là:

```text
Tác vụ cha                     Tác vụ lấy giá          Tác vụ tồn kho
    │                               │                       │
    ├─ fork ───────────────────────>│                       │
    ├─ fork ───────────────────────────────────────────────>│
    ├─ join: chờ kết quả             │                       │
    │                               └─ ném IOException      │
    │                                      │                │
    │                         scope ghi nhận lỗi và hủy     │
    │                                      └─ interrupt ───>│
    │                                                       ├─ thoát chờ
    ├─ join ném ExecutionException                          ├─ dọn dẹp
    ├─ close: chờ các luồng con kết thúc                     └─ kết thúc
    └─ xử lý lỗi sau khi đã đóng scope
```

Sơ đồ thể hiện quan hệ cần thiết, không ấn định thứ tự tuyệt đối giữa thời điểm `join()` ném lỗi và thời điểm tác vụ tồn kho dọn dẹp. Tác vụ con có thể đã kết thúc trước khi cha bắt đầu `close()`, hoặc cha phải chờ thêm.

Điểm bảo đảm là khi đã đi qua `close()`, các luồng tác vụ con của scope đã kết thúc. Vì vậy, hãy đặt phần bắt lỗi của toàn bộ thao tác **bên ngoài `try-with-resources`** nếu tầng đó cần xử lý sau khi nhóm tác vụ đã được dọn dẹp.

Với chính sách mặc định, lỗi được chọn là lỗi của tác vụ thất bại đầu tiên theo hợp đồng API. Nếu nhiều tác vụ lỗi gần nhau, không nên suy ra lỗi được chọn từ thứ tự gọi `fork`. Scope cũng không mặc nhiên cung cấp một danh sách chứa mọi lỗi đồng thời.

## 3. Ví dụ đầy đủ: một tác vụ lỗi, tác vụ còn lại được ngắt

Ví dụ sau mô phỏng việc lấy giá thất bại khi tác vụ tồn kho đang chờ một sự kiện. `CountDownLatch` giúp phối hợp ví dụ mà không cần đoán tác vụ nào được lập lịch trước.

Lưu thành `FailureCancellationDemo.java` trong môi trường học có JDK 27:

```java
import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

public class FailureCancellationDemo {
    record Offer(String price, String inventory) {
    }

    static Offer loadOffer()
            throws InterruptedException, ExecutionException {
        CountDownLatch inventoryStarted = new CountDownLatch(1);

        try (var scope = StructuredTaskScope.open()) {
            var price = scope.fork(() -> loadPrice(inventoryStarted));
            var inventory = scope.fork(() -> loadInventory(inventoryStarted));

            scope.join();

            return new Offer(price.get(), inventory.get());
        }
    }

    static String loadPrice(CountDownLatch inventoryStarted)
            throws InterruptedException, IOException {
        inventoryStarted.await();
        throw new IOException("price-service-unavailable");
    }

    static String loadInventory(CountDownLatch inventoryStarted)
            throws InterruptedException {
        try {
            inventoryStarted.countDown();

            // Mô phỏng một thao tác chờ chưa có kết quả.
            // Không có bên nào countDown latch này; interruption sẽ kết thúc chờ.
            CountDownLatch inventoryResult = new CountDownLatch(1);
            inventoryResult.await();
            return "in-stock";
        } finally {
            System.out.println("inventory: đã dọn dẹp");
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(loadOffer());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.out.println("Luồng xử lý yêu cầu đã bị ngắt");
        } catch (ExecutionException e) {
            System.out.println("Yêu cầu thất bại: " + e.getCause());
        }
    }
}
```

Biên dịch và chạy bằng công cụ của cùng JDK 27:

```shell
javac --enable-preview --release 27 FailureCancellationDemo.java
java --enable-preview FailureCancellationDemo
```

Nếu không có interruption từ bên ngoài, kết quả dự kiến là:

```text
inventory: đã dọn dẹp
Yêu cầu thất bại: java.io.IOException: price-service-unavailable
```

Trong ví dụ, `inventoryStarted` là tín hiệu rằng tác vụ tồn kho đã đi vào phần công việc của nó. `loadPrice` chỉ ném lỗi sau tín hiệu này. Nếu interruption đến trước lúc `inventoryResult.await()` bắt đầu chờ, phương thức chờ vẫn nhận ra trạng thái ngắt và ném `InterruptedException`.

Các latch được tạo mới cho mỗi lần xử lý, tránh dùng nhầm tín hiệu giữa hai yêu cầu. Hợp đồng chờ, đánh thức và interruption của latch được mô tả tại [CountDownLatch của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

`loadInventory` để `InterruptedException` lan truyền và dùng `finally` cho phần dọn dẹp. Dòng in chỉ đánh dấu thời điểm dọn dẹp trong ví dụ; ứng dụng thực tế cần giải phóng tài nguyên mà tác vụ sở hữu. Dòng báo lỗi của `main` xuất hiện sau đó vì `loadOffer` đã đóng scope trước khi trả lỗi về cho `main`.

Hai lời gọi `price.get()` và `inventory.get()` chỉ nằm trên đường `join()` thành công. Chúng không được thực thi khi lấy giá thất bại. Điều kiện đọc kết quả được quy định trong [StructuredTaskScope.Subtask của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html).

## 4. Bắt đúng lỗi ở đúng luồng

### 4.1. Lỗi của tác vụ con đi qua ExecutionException

`ExecutionException` là lớp bọc để chuyển lỗi của một tác vụ về nơi nhận kết quả. Muốn phân loại lỗi gốc, hãy kiểm tra `getCause()` và giữ nguyên chuỗi nguyên nhân khi chuyển đổi exception. Hợp đồng cơ bản được mô tả tại [ExecutionException của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutionException.html).

Ví dụ, khi tầng ứng dụng quyết định chuyển lỗi sang exception của nó, cách sau giữ được dấu vết chẩn đoán:

```java
catch (ExecutionException e) {
    throw new IllegalStateException("Không tổng hợp được kết quả chào hàng", e);
}
```

Đây là một đoạn `catch` dùng trong phương thức bao quanh lời gọi `loadOffer`, không phải một chương trình độc lập. Việc giữ cả exception bọc giúp giữ được dấu vết tại điểm chờ; `cause` bên trong vẫn dẫn về tác vụ con.

Không nên chỉ dùng `new IllegalStateException(e.getMessage())`, vì cách đó bỏ chuỗi nguyên nhân. Cũng không nên trả một kết quả thành công rỗng cho mọi lỗi của tác vụ con: thất bại của dữ liệu bắt buộc cần tiếp tục biểu hiện là thất bại của yêu cầu.

### 4.2. InterruptedException trực tiếp cho biết luồng cha bị ngắt

Khi `join()` ném trực tiếp `InterruptedException`, luồng bị ngắt là luồng đang gọi `join()`. Nó đã được yêu cầu dừng hoạt động chờ; ứng dụng phải xử lý tín hiệu này theo hợp đồng của tầng gọi.

Việc `join()` ngừng chờ vì interruption không nên được coi là đủ để hoàn tất hủy mọi công việc con. Trong mẫu `try-with-resources`, exception làm luồng điều khiển rời khối `try`, rồi `close()` hủy phần chưa hoàn tất và chờ các luồng con kết thúc.

Nếu bắt interruption ngay bên trong khối `try` rồi tiếp tục xử lý như bình thường, chương trình có thể kéo dài công việc sau yêu cầu hủy. Chỉ lặp lại `join()` khi ứng dụng có chủ đích rõ ràng để tiếp tục chờ; hợp đồng cho phép thử lại sau interruption không phải lý do mặc định để bỏ qua tín hiệu dừng.

### 4.3. Cause là InterruptedException không chứng minh cha đã bị ngắt

Một tác vụ con có thể tự nhận interruption và kết thúc bằng `InterruptedException`. Nếu lỗi đó được chính sách scope chọn làm lỗi kết quả, cha có thể nhận `ExecutionException` với `InterruptedException` trong `cause`.

Đó là thông tin về **luồng con**. Không tự gọi `Thread.currentThread().interrupt()` trên cha chỉ vì tìm thấy `InterruptedException` trong chuỗi nguyên nhân của lỗi con. Cha chỉ khôi phục tín hiệu ngắt của chính nó khi luồng cha thực sự đang xử lý interruption của mình.

| Tín hiệu tại cha | Cách diễn giải |
| --- | --- |
| `join()` ném trực tiếp `InterruptedException` | Luồng cha bị ngắt khi thực hiện thao tác chờ. |
| `ExecutionException` có cause là lỗi I/O | Tác vụ con được chọn đã thất bại vì lỗi I/O. |
| `ExecutionException` có cause là `InterruptedException` | Một tác vụ con đã kết thúc bằng interruption; không tự suy ra trạng thái ngắt của cha. |
| `ExecutionException` có cause là `CancelledByTimeoutException` | Với chính sách mặc định của JDK 27, thời hạn của scope đã hết. |

Nếu lỗi con, timeout và interruption của cha xảy ra gần nhau, không dựa vào một thứ tự thắng cố định để viết logic nghiệp vụ. Hãy xử lý đúng từng kết quả được API trả về và vẫn bảo đảm đóng scope.

## 5. Xử lý InterruptedException theo hợp đồng của tầng hiện tại

Interruption là cơ chế hợp tác: mỗi luồng có một trạng thái ngắt, được đặt bởi `interrupt()`. Nhiều phương thức chờ có thể ném `InterruptedException` và xóa trạng thái ngắt trước khi ném. Cần phân biệt việc truyền exception với việc giữ trạng thái ngắt cho mã tiếp theo. Các quy tắc này được mô tả trong [InterruptedException của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/InterruptedException.html).

### 5.1. Nếu phương thức cho phép ném tiếp, hãy lan truyền interruption

`loadOffer` trong ví dụ khai báo:

```java
static Offer loadOffer()
        throws InterruptedException, ExecutionException
```

Khi `join()` bị ngắt, phương thức để `InterruptedException` đi tiếp sau khi tài nguyên được đóng. Đây là một hợp đồng rõ ràng: tầng gọi biết hoạt động đã bị yêu cầu dừng.

Không cần thêm một `catch` chỉ để ném lại đúng exception đó. Cũng không có quy tắc bắt buộc phải khôi phục cờ trước mỗi lần ném tiếp `InterruptedException`; bản thân checked exception đang truyền tín hiệu tới tầng có trách nhiệm xử lý.

### 5.2. Nếu không thể ném tiếp, khôi phục cờ rồi kết thúc công việc

Một callback kiểu `Runnable` không khai báo checked exception. Khi sử dụng `loadOffer` trong callback đó, có thể áp dụng mẫu sau. Đoạn này dùng lại các khai báo của `FailureCancellationDemo`:

```java
Runnable requestJob = () -> {
    try {
        Offer offer = loadOffer();
        System.out.println(offer);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    } catch (ExecutionException e) {
        throw new IllegalStateException("Xử lý yêu cầu thất bại", e);
    }
};
```

`return` kết thúc callback sau yêu cầu dừng. Khôi phục cờ rồi tiếp tục một vòng lặp retry vô hạn vẫn là cách phản hồi hủy kém: những thao tác chờ tiếp theo có thể lại bị ngắt ngay và tạo vòng lặp lỗi.

Tại biên sở hữu luồng, ứng dụng có thể có chính sách kết thúc chuyên biệt. Với mã thư viện hoặc callback mà bên ngoài còn quan sát trạng thái luồng, khôi phục cờ giúp tín hiệu không bị mất.

### 5.3. Nếu chuyển thành exception khác, vẫn giữ tín hiệu ngắt

Một tầng không cho phép ném checked exception có thể cần chuyển thành exception riêng. Khi đó, giữ nguyên nguyên nhân và khôi phục cờ trước khi ném:

```java
catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Yêu cầu đã bị ngắt", e);
}
```

Việc đổi tên loại exception không làm mất trách nhiệm xử lý interruption. Ngược lại, mẫu bắt `Exception` chung rồi trả giá trị mặc định dễ che cả tín hiệu hủy lẫn lỗi thật; hãy tách nhánh interruption khi hợp đồng cần phân biệt chúng.

## 6. Viết tác vụ con có khả năng hợp tác khi bị hủy

### 6.1. Với thao tác chờ, để interruption thoát ra

Các phương thức như `CountDownLatch.await()`, `Thread.sleep()` hoặc thao tác chờ interruptible của các cấu trúc đồng thời cho phép tác vụ phản hồi ngắt. Nếu tác vụ đã khai báo `throws InterruptedException`, thường có thể để exception lan truyền và dọn dẹp trong `finally` hoặc `try-with-resources`.

Một kiểu xử lý cần tránh là:

```java
try {
    Thread.sleep(10_000);
} catch (InterruptedException e) {
    // Bỏ qua rồi tiếp tục làm công việc như chưa có yêu cầu hủy.
}
```

Vấn đề nằm ở việc mất tín hiệu dừng và tiếp tục công việc. Với API I/O, cần đọc hợp đồng cụ thể: không phải mọi thao tác blocking đều ném `InterruptedException`; một số cơ chế trả exception I/O hoặc có cách hủy riêng. Cấu hình timeout và khả năng hủy của thư viện vẫn là trách nhiệm của ứng dụng.

### 6.2. Với vòng tính toán, kiểm tra trạng thái ngắt

Mã chỉ tính toán có thể không gọi phương thức interruptible nào. Khi đó, nó cần chủ động kiểm tra trạng thái ngắt ở những điểm phù hợp:

```java
static long sumUntil(long upperBound) throws InterruptedException {
    long sum = 0;

    for (long value = 0; value < upperBound; value++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Phép tính đã bị hủy");
        }
        sum += value;
    }

    return sum;
}
```

Đây là ví dụ về điểm kiểm tra hủy, không phải một thuật toán cộng tối ưu. Trong công việc thực tế, có thể kiểm tra giữa các khối dữ liệu đủ nhỏ để độ trễ phản hồi hủy chấp nhận được.

`isInterrupted()` đọc trạng thái mà không xóa nó. `Thread.interrupted()` đọc **và xóa** trạng thái ngắt của luồng hiện tại, nên không dùng thay thế một cách vô thức. Hành vi của cả hai được quy định trong phần [Thread Interruption của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html).

### 6.3. Dọn dẹp cũng là một phần của độ trễ hủy

Tác vụ có thể phản hồi ngắt rất nhanh nhưng sau đó thực hiện cleanup quá lâu. Hãy giữ cleanup giới hạn trong việc giải phóng những tài nguyên tác vụ sở hữu; tránh mở một luồng retry hoặc chờ một dịch vụ khác không có thời hạn chỉ để kết thúc tác vụ đang bị hủy.

Nếu cleanup tự ném exception, lỗi nhìn thấy từ tác vụ có thể thay đổi hoặc có thêm suppressed exceptions tùy cấu trúc quản lý tài nguyên. Giữ đủ chuỗi nguyên nhân khi ghi nhận lỗi để không mất thông tin về cả công việc chính và dọn dẹp.

## 7. join và close có vai trò khác nhau khi bị ngắt

`join()` là nơi nhận kết quả theo chính sách scope; nó có thể dừng chờ bằng `InterruptedException`. Khi ném exception này, trạng thái ngắt của luồng gọi đã được xóa theo hợp đồng.

`close()` là hàng rào vòng đời. Nó hủy phần còn chạy rồi chờ các luồng con kết thúc. Nếu luồng cha lại bị ngắt trong lúc `close()` chờ, phương thức vẫn tiếp tục chờ và hoàn tất với trạng thái ngắt được đặt.

Hành vi chờ khi đóng scope cũng được mô tả tại [StructuredTaskScope.close của Java 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#close()); bài chỉ đối chiếu quy tắc vòng đời còn áp dụng, không sử dụng chữ ký xử lý lỗi preview cũ.

Hai hệ quả thực tế:

1. Không thể dùng interruption thêm một lần như một cách buộc `close()` bỏ mặc các luồng con.
2. Không được giả định rằng lần interruption đã khiến `join()` ném lỗi sẽ luôn được `close()` tự đặt lại cờ. Nếu tín hiệu đó đã được `join()` xóa và không có lần ngắt mới trong lúc đóng, tầng bắt `InterruptedException` vẫn phải thực hiện chính sách lan truyền hoặc khôi phục của mình.

Đồng thời, `close()` không thay thế nghĩa vụ gọi `join()` sau khi fork. Bỏ qua `join()` rồi dựa vào `close()` có thể dẫn đến `IllegalStateException` sau khi scope được đóng. Các thao tác `fork`, `join` và `close` thuộc trách nhiệm của luồng sở hữu scope.

## 8. Timeout là lý do hủy riêng, không phải interruption của cha

JDK 27 cho phép mở scope với thời hạn qua `withTimeout(Duration)`. Thời hạn bắt đầu từ lúc mở scope, nên cả thời gian fork công việc cũng nằm trong khoảng đó. Cấu hình được mô tả tại [StructuredTaskScope.Configuration](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html).

Đoạn dưới minh họa timeout; cần import `java.time.Duration` và đặt trong một phương thức khai báo `throws InterruptedException, ExecutionException`, bên cạnh các import đã có trong ví dụ đầy đủ:

```java
try (var scope = StructuredTaskScope.open(
        config -> config.withTimeout(Duration.ofMillis(500)))) {
    var slowTask = scope.fork(() -> {
        Thread.sleep(10_000);
        return "done";
    });

    scope.join();
    System.out.println(slowTask.get());
} catch (ExecutionException e) {
    if (e.getCause()
            instanceof StructuredTaskScope.CancelledByTimeoutException) {
        System.out.println("Đã hết thời hạn của scope");
    } else {
        throw e;
    }
}
```

Theo chính sách mặc định của Java 27, `join()` báo timeout bằng `ExecutionException` có cause là `StructuredTaskScope.CancelledByTimeoutException`. Đây là kết quả do thời hạn của scope, không phải bằng chứng luồng cha đã nhận interruption; không tự đặt cờ ngắt của cha trong nhánh timeout. Vai trò của exception này được nêu tại [CancelledByTimeoutException của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.CancelledByTimeoutException.html).

Mốc 500 ms giới hạn thời điểm bắt đầu hủy do hết hạn, không bảo đảm phương thức bao quanh trả về trong đúng 500 ms. Tác vụ con vẫn phải phản hồi ngắt và hoàn tất cleanup trước khi `close()` kết thúc.

Nếu ứng dụng đã có deadline cho toàn yêu cầu, các scope con cần dùng phần thời gian còn lại. Tạo lại một timeout đầy đủ ở mỗi tầng có thể khiến tổng thời gian vượt ngân sách ban đầu. Độ trễ phản hồi hủy còn phụ thuộc thư viện I/O, những đoạn tính toán giữa hai lần kiểm tra ngắt và phần cleanup.

## 9. Scope lồng nhau và lựa chọn chính sách lỗi

Một tác vụ con có thể mở task scope riêng để chia công việc thành các tác vụ nhỏ hơn. Với cách dùng `try-with-resources` ở từng tầng:

```text
Scope ngoài
├─ Tác vụ A
│  └─ Scope trong
│     ├─ A1
│     └─ A2
└─ Tác vụ B
```

Nếu B thất bại, scope ngoài có thể ngắt luồng chạy A. Nếu A đang chờ `join()` của scope trong, nó nhận interruption, rời khối `try`, đóng scope trong và chờ A1, A2 kết thúc trước khi chính A kết thúc.

Vì vậy, khả năng hủy cần được giữ xuyên suốt các tầng. Một `catch` trong A nuốt interruption có thể làm chậm cả cây công việc. Cũng cần giữ các công việc thuộc yêu cầu ở trong cây scope; một luồng hoặc job được tự tách ra ngoài không tự nhận mọi bảo đảm vòng đời của scope đang xét.

Việc cần hủy khi một nhánh lỗi phụ thuộc yêu cầu nghiệp vụ. Với dữ liệu bắt buộc như giá và tồn kho trong ví dụ, chính sách mặc định phù hợp. Nếu chỉ cần một kết quả thành công trong nhiều nguồn tương đương, `Joiner.anySuccessfulOrThrow()` có chính sách khác: một nhánh thất bại chưa đủ để kết luận toàn bộ thao tác thất bại.

Không suy rộng câu “một tác vụ lỗi thì hủy tất cả” cho mọi `Joiner`. Joiner quyết định cách chọn kết quả và thời điểm hủy; một joiner tùy chỉnh còn có thể chọn exception khác. Các chính sách và điều kiện được mô tả tại [StructuredTaskScope.Joiner của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html).

Khi một nhánh trả fallback thay vì ném lỗi, scope nhìn thấy nhánh đó thành công. Chỉ làm vậy với lỗi mà hợp đồng nghiệp vụ thực sự cho phép phục hồi. Interruption và hủy yêu cầu cần tiếp tục giữ ý nghĩa dừng công việc, thay vì bị chuyển thành một kết quả fallback rồi tiếp tục hoạt động.

## 10. Các quyết định cần rõ khi đưa vào dịch vụ

**Đặt ranh giới sở hữu scope ở nơi tổng hợp kết quả.** Phương thức đó quyết định nhánh nào bắt buộc, nhánh nào được phép có kết quả thiếu và lỗi nào cần đưa lên tầng gọi. Các tác vụ con chịu trách nhiệm làm việc, phản hồi ngắt và dọn tài nguyên mà chúng sở hữu.

**Phân loại nguyên nhân và hệ quả khi quan sát lỗi.** Một lỗi gọi dịch vụ có thể dẫn đến nhiều nhánh anh em nhận interruption. Nếu ghi mọi nhánh bị ngắt thành lỗi gốc độc lập, hệ thống giám sát sẽ tạo nhiều tín hiệu cho một sự cố. Hãy giữ lỗi đã khởi phát việc hủy, định danh nhánh và ngữ cảnh yêu cầu; interruption do hủy các nhánh còn lại là thông tin về vòng đời công việc.

**Không đọc mọi handle như thể chúng đều có kết quả sau hủy.** `Subtask.State` có `SUCCESS`, `FAILED` và `UNAVAILABLE`; không có cam kết rằng tác vụ bị hủy sẽ luôn có một exception để đọc. Chỉ truy xuất kết quả hoặc lỗi khi trạng thái và hợp đồng truy xuất cho phép. Các trạng thái được định nghĩa tại [StructuredTaskScope.Subtask.State](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.State.html).

**Tách việc hủy khỏi hoàn tác tác động bên ngoài.** Nếu tác vụ đã ghi dữ liệu hoặc gửi một yêu cầu thay đổi trạng thái sang dịch vụ khác, interruption không tự đảo ngược tác động đã xảy ra. Các thao tác đó vẫn cần hợp đồng giao dịch, khả năng gọi lặp an toàn hoặc cơ chế bù phù hợp với nghiệp vụ.

| Cách xử lý dễ sai | Hệ quả | Cách tổ chức phù hợp |
| --- | --- | --- |
| Bắt `Exception` chung rồi trả thành công rỗng | Lỗi bắt buộc và interruption có thể bị che mất | Tách interruption và chỉ phục hồi các lỗi được hợp đồng cho phép. |
| Bắt `InterruptedException`, ghi log rồi retry mãi | Tác vụ không hợp tác khi scope hủy | Ném tiếp hoặc khôi phục cờ rồi kết thúc theo hợp đồng. |
| Gọi `interrupt()` trên cha vì cause của lỗi con là `InterruptedException` | Tạo tín hiệu ngắt sai luồng | Phân biệt exception của con với interruption trực tiếp của cha. |
| Cho rằng `isCancelled()` nghĩa là mọi luồng đã dừng | Xử lý tiếp khi cleanup còn chạy | Dựa vào việc hoàn tất đóng scope để xác định vòng đời đã kết thúc. |
| Mong `close()` bỏ chờ khi bị ngắt | Phương thức vẫn chờ tác vụ không chịu dừng | Bảo đảm tác vụ và cleanup phản hồi hủy. |
| Đọc mọi `Subtask.get()` sau một `join()` thất bại | Có thể gặp lỗi trạng thái thay vì kết quả | Chỉ đọc trên đường và trạng thái được hợp đồng cho phép. |
| Dùng timeout scope như cam kết thời gian trả về tuyệt đối | Yêu cầu có thể vượt thời gian vì chờ dọn dẹp | Tính cả thời gian phản hồi hủy và cleanup trong thiết kế. |
| Giữ công việc thuộc yêu cầu trong một luồng tự tách rời | Công việc có thể tiếp tục sau khi scope đã đóng | Đặt công việc đó trong task scope, hoặc thiết kế thành job có vòng đời riêng rõ ràng. |
