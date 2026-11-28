# Kiểm thử truy cập cạnh tranh, lỗi và số lần tính giá trị

LazyConstant là một holder chỉ nhận một giá trị và giữ nguyên giá trị đó sau khi khởi tạo thành công. Trong JDK 26, giá trị chỉ được tính khi có lời gọi get() đầu tiên. Nếu nhiều thread cùng gọi get(), chỉ một thread được chọn để chạy computing function; các thread còn lại chờ kết quả. Điều này giúp tránh việc khởi tạo trùng lặp và bảo đảm đối tượng được công bố an toàn cho các thread khác.

Bài này hướng dẫn kiểm thử ba đặc tính quan trọng: nhiều thread cùng truy cập, computing function thất bại và số lần function thực sự được gọi. Nội dung tập trung vào API preview của JDK 26 theo JEP 526 – Lazy Constants (Second Preview). Vì JDK 27 đã thay đổi một số quy tắc lỗi và API, bài cũng chỉ rõ khác biệt khi nâng cấp để kết quả kiểm thử không bị hiểu sai.

## 1. Xác định phiên bản và bật preview

LazyConstant thuộc package java.lang, được bổ sung dưới dạng preview API trong JDK 26. Dùng đúng JDK 26 để biên dịch và chạy ví dụ:

~~~powershell
javac --enable-preview --release 26 -d out src\LazyConstantCheck.java
java --enable-preview -cp out LazyConstantCheck
~~~

Trong JDK 26, các thành phần cần chú ý là:

| API | Công dụng |
|---|---|
| LazyConstant.of(Supplier) | Tạo holder chưa có giá trị và lưu computing function |
| get() | Tính giá trị nếu chưa khởi tạo, sau đó trả lại giá trị đã lưu |
| isInitialized() | Kiểm tra holder đã khởi tạo hay chưa mà không kích hoạt tính toán |
| orElse(other) | Trả giá trị đã khởi tạo hoặc giá trị thay thế; không kích hoạt tính toán |

LazyConstant là preview API. Mã dùng API này phải bật preview ở cả compiler và runtime. Không thể biên dịch bằng JDK 27 với --release 26 để dùng preview của JDK 26; compiler và runtime phải cùng release với preview đang thử nghiệm.

Tính đến ngày 27/11/2026, JDK 27 đã GA và Lazy Constants tiếp tục ở preview lần thứ ba theo JEP 531. JDK 27 đã thay đổi hành vi khi computing function thất bại và bỏ hai phương thức isInitialized() và orElse(). Phần kiểm thử chính bên dưới dùng API JDK 26; phần cuối bài mô tả cách điều chỉnh khi nâng cấp.

## 2. Những bất biến cần kiểm tra trong JDK 26

Một lazy constant mới được tạo chưa có nội dung. Gọi get() lần đầu sẽ thực thi computing function. Nếu function trả về một giá trị khác null, holder được khởi tạo và mọi lần gọi get() thành công sau đó đều nhận cùng nội dung.

Các bất biến quan trọng:

1. **Khởi tạo trễ:** gọi LazyConstant.of() không chạy computing function.
2. **Khởi tạo tối đa một lần khi thành công:** nhiều thread cạnh tranh chỉ có một thread chạy computing function cho lần khởi tạo thành công.
3. **Một giá trị duy nhất:** sau khi khởi tạo, nội dung không thể bị thay thế bằng kết quả khác.
4. **Công bố an toàn:** việc chạy computing function và khởi tạo nội dung xảy ra trước khi thread khác đọc nội dung đã khởi tạo (happens-before).
5. **Không lưu null:** nếu computing function trả về null, get() ném NullPointerException; holder không thể chứa giá trị null.
6. **Lỗi từ computing function không bị cache trong JDK 26:** nếu computing function ném exception hoặc Error, throwable được truyền về caller và holder vẫn chưa được khởi tạo. Một lần gọi get() sau đó có thể chạy lại function.
7. **Tự gọi đệ quy:** nếu computing function trực tiếp hoặc gián tiếp gọi lại get() của chính lazy constant đó, get() ném IllegalStateException và holder không được khởi tạo.

Cần phân biệt số lần tính toán với số lần khởi tạo thành công. Khi function thành công, nó chỉ chạy một lần. Khi function thất bại, lần gọi get() sau có thể thử lại; vì thế tổng số lần function được gọi có thể lớn hơn một.

## 3. Kiểm tra khởi tạo trễ và số lần tính toán cơ bản

Dùng AtomicInteger để đếm số lần computing function được gọi. Không dùng biến int thông thường nếu nhiều thread có thể cùng cập nhật bộ đếm.

~~~java
import java.lang.LazyConstant;
import java.util.concurrent.atomic.AtomicInteger;

public class LazyConstantBasicCheck {

    public static void main(String[] args) {
        AtomicInteger computations = new AtomicInteger();

        LazyConstant<String> endpoint = LazyConstant.of(() -> {
            computations.incrementAndGet();
            return "https://api.example.test";
        });

        check(computations.get() == 0,
                "of() không được tính giá trị ngay");
        check(!endpoint.isInitialized(),
                "Holder mới phải ở trạng thái chưa khởi tạo");
        check(endpoint.orElse("fallback").equals("fallback"),
                "orElse() phải trả fallback khi chưa khởi tạo");
        check(computations.get() == 0,
                "isInitialized() và orElse() không được kích hoạt tính toán");

        String first = endpoint.get();

        check(first.equals("https://api.example.test"),
                "Giá trị đầu tiên không đúng");
        check(endpoint.isInitialized(),
                "Holder phải được khởi tạo sau get() thành công");

        String second = endpoint.get();

        check(first == second,
                "Các lần get() phải trả cùng một object");
        check(computations.get() == 1,
                "Function thành công chỉ được chạy một lần");

        System.out.println("PASS: lazy initialization");
        System.out.println("Computations: " + computations.get());
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Các điểm cần quan sát:

- Sau LazyConstant.of(), bộ đếm vẫn bằng 0.
- isInitialized() trả false khi holder chưa có giá trị.
- orElse("fallback") trả fallback và không gọi computing function.
- get() đầu tiên làm bộ đếm tăng lên 1.
- get() tiếp theo trả lại đúng object đã lưu, không tính lại.

Dùng phép so sánh tham chiếu == trong ví dụ vì mục tiêu là xác nhận cùng một object được giữ lại, không chỉ hai object có nội dung bằng nhau. Với kiểu dữ liệu bất biến có equals() phù hợp, có thể kiểm tra thêm equality, nhưng điều đó không thay thế kiểm tra identity khi cần chứng minh chỉ một instance được tạo.

## 4. Kiểm thử nhiều thread cùng gọi get()

Kiểm thử cạnh tranh cần tạo tình huống nhiều thread cùng đến điểm gọi get() khi computing function đầu tiên vẫn đang chạy. Nếu chỉ tạo nhiều task rồi để function hoàn tất quá nhanh, các task có thể lần lượt đọc giá trị đã khởi tạo; phép thử đó chưa tạo được áp lực cạnh tranh đủ rõ.

Dùng CountDownLatch để điều phối:

- ready: tất cả worker đã sẵn sàng.
- start: cho các worker bắt đầu cùng lúc.
- supplierEntered: báo computing function đã bắt đầu.
- atGet: các worker đã tiến đến ngay trước lời gọi get().
- releaseSupplier: giữ computing function chưa trả về cho đến khi các worker còn lại đã tiến đến get().

Ví dụ kiểm thử hoàn chỉnh:

~~~java
import java.lang.LazyConstant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class LazyConstantConcurrencyCheck {

    record Config(String endpoint) {}

    public static void main(String[] args) throws Exception {
        int workerCount = 8;

        AtomicInteger computations = new AtomicInteger();
        CountDownLatch ready = new CountDownLatch(workerCount);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch atGet = new CountDownLatch(workerCount);
        CountDownLatch supplierEntered = new CountDownLatch(1);
        CountDownLatch releaseSupplier = new CountDownLatch(1);

        Config expected = new Config("https://api.example.test");

        LazyConstant<Config> config = LazyConstant.of(() -> {
            computations.incrementAndGet();
            supplierEntered.countDown();
            awaitUninterruptibly(releaseSupplier);
            return expected;
        });

        ExecutorService executor =
                Executors.newFixedThreadPool(workerCount);

        try (executor) {
            try {
                List<Future<Config>> results = new ArrayList<>();

                for (int i = 0; i < workerCount; i++) {
                    Future<Config> result = executor.submit(() -> {
                        ready.countDown();

                        if (!start.await(5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                    "Không nhận được tín hiệu bắt đầu");
                        }

                        atGet.countDown();
                        return config.get();
                    });

                    results.add(result);
                }

                if (!ready.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Worker chưa sẵn sàng");
                }

                start.countDown();

                if (!supplierEntered.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError(
                            "Computing function chưa được gọi");
                }

                if (!atGet.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError(
                            "Không phải tất cả worker tiến đến get()");
                }

                // Giải phóng function sau khi các worker đã cùng tiến đến get().
                releaseSupplier.countDown();

                for (Future<Config> result : results) {
                    Config actual = result.get(10, TimeUnit.SECONDS);

                    check(actual == expected,
                            "Worker nhận một instance khác");
                }
            } finally {
                // Mở latch trước khi close() chờ các worker kết thúc.
                start.countDown();
                releaseSupplier.countDown();
            }
        }

        check(computations.get() == 1,
                "Chỉ một thread được chạy computing function");
        check(config.isInitialized(),
                "Holder phải được khởi tạo sau khi function thành công");
        check(config.get() == expected,
                "Lần get() sau phải trả cùng nội dung");

        System.out.println("PASS: concurrent initialization");
        System.out.println("Workers: " + workerCount);
        System.out.println("Computations: " + computations.get());
    }

    private static void awaitUninterruptibly(CountDownLatch latch) {
        boolean interrupted = false;

        while (true) {
            try {
                latch.await();
                break;
            } catch (InterruptedException exception) {
                interrupted = true;
            }
        }

        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
PASS: concurrent initialization
Workers: 8
Computations: 1
~~~

Tất cả Future phải trả về cùng object expected. Bộ đếm computations phải bằng 1, dù có tám thread gọi get() gần như đồng thời.

CountDownLatch ở đây dùng để tạo một cửa sổ cạnh tranh có kiểm soát. atGet báo worker đã đến ngay trước lệnh get(); nó không phải API để quan sát trạng thái lock bên trong LazyConstant. Không viết test phụ thuộc vào số thread đang BLOCKED, tên thread, monitor hoặc cấu trúc nội bộ của JDK vì các chi tiết đó không thuộc hợp đồng API.

### Công bố an toàn và dữ liệu bên trong object

LazyConstant bảo đảm nội dung được khởi tạo an toàn và việc khởi tạo xảy ra-before các thread đọc nội dung. Các final field của object vừa tạo cũng được công bố an toàn.

Tuy nhiên, holder chỉ bảo đảm tham chiếu/nội dung được thiết lập một lần; nó không tự biến object được giữ thành immutable sâu. Ví dụ, nếu holder chứa một ArrayList, các thread vẫn có thể sửa ArrayList đó và cần cơ chế đồng bộ phù hợp.

Không dùng một phép kiểm tra đồng thời chỉ đọc một field không-final đang bị thay đổi để kết luận LazyConstant có lỗi công bố dữ liệu. Hãy tách hai vấn đề: công bố object ban đầu và đồng bộ các mutation xảy ra sau đó.

## 5. Kiểm thử exception và khả năng thử lại trong JDK 26

Trong JDK 26, khi computing function ném unchecked exception hoặc Error, get() truyền throwable đó về caller. Lazy constant không chuyển sang trạng thái đã khởi tạo và không lưu exception làm nội dung. Một lời gọi get() sau đó có thể thực hiện lại phép tính.

Ví dụ function lỗi ở lần đầu rồi thành công ở lần thứ hai:

~~~java
import java.lang.LazyConstant;
import java.util.concurrent.atomic.AtomicInteger;

public class LazyConstantRetryCheck {

    public static void main(String[] args) {
        AtomicInteger attempts = new AtomicInteger();

        LazyConstant<String> service = LazyConstant.of(() -> {
            int attempt = attempts.incrementAndGet();

            if (attempt == 1) {
                throw new IllegalStateException("Temporary failure");
            }

            return "service-ready";
        });

        boolean firstCallFailed = false;

        try {
            service.get();
        } catch (IllegalStateException expected) {
            firstCallFailed = true;
            check("Temporary failure".equals(expected.getMessage()),
                    "Throwable ban đầu phải được truyền về caller");
        }

        check(firstCallFailed,
                "Lần đầu phải phát sinh IllegalStateException");
        check(!service.isInitialized(),
                "Lỗi không được làm holder chuyển sang initialized");
        check(attempts.get() == 1,
                "Lần đầu chỉ có một lần thực thi function");

        String value = service.get();

        check(value.equals("service-ready"),
                "Lần thử lại phải trả giá trị thành công");
        check(service.isInitialized(),
                "Holder phải được khởi tạo sau lần thử thành công");
        check(attempts.get() == 2,
                "Function phải được gọi lại sau thất bại");

        check(service.get() == value,
                "Lần đọc tiếp theo phải dùng lại giá trị");
        check(attempts.get() == 2,
                "Không được tính lại sau khi đã khởi tạo");

        System.out.println("PASS: exception and retry");
        System.out.println("Computations: " + attempts.get());
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
PASS: exception and retry
Computations: 2
~~~

Phép thử chứng minh:

- Lần đầu function chạy và ném IllegalStateException.
- Throwable được truyền về caller.
- Holder vẫn chưa được khởi tạo.
- Lần get() sau gọi function lần thứ hai.
- Khi lần thứ hai thành công, holder giữ kết quả và không tính lại.

Không diễn giải “at most once” thành “computing function chắc chắn chỉ được gọi đúng một lần trong toàn bộ vòng đời”. Cam kết là khởi tạo nội dung thành công tối đa một lần và chỉ một thread chạy function tại một thời điểm cho một lần cạnh tranh. Nếu các lần tính toán thất bại, JDK 26 cho phép các lần get() sau thử lại.

## 6. Kiểm thử Error, null và gọi đệ quy

### Computing function ném Error

Supplier có thể ném Error vì Error là unchecked throwable. Trong JDK 26, Error được truyền về caller và holder vẫn chưa được khởi tạo. Nếu caller gọi get() lần nữa, function có thể được thực hiện lại.

~~~java
AtomicInteger attempts = new AtomicInteger();

LazyConstant<String> value = LazyConstant.of(() -> {
    attempts.incrementAndGet();
    throw new AssertionError("Initialization failed");
});

boolean firstFailed = false;

try {
    value.get();
} catch (AssertionError expected) {
    firstFailed = true;
}

check(firstFailed, "Error phải được truyền về caller");
check(!value.isInitialized(), "Holder vẫn chưa khởi tạo");

boolean secondFailed = false;

try {
    value.get();
} catch (AssertionError expected) {
    secondFailed = true;
}

check(secondFailed, "Lần gọi sau có thể chạy function lại");
check(attempts.get() == 2, "Function đã chạy hai lần");
~~~

Đây là kiểm thử semantics của API, không phải khuyến nghị retry mọi Error trong ứng dụng. Các lỗi như OutOfMemoryError hoặc LinkageError thường cần xử lý ở cấp ứng dụng/JVM; việc gọi get() lại một cách mù quáng có thể làm tình hình nghiêm trọng hơn.

### Computing function trả về null

LazyConstant không cho phép nội dung null. JDK 26 ném NullPointerException nếu computing function trả về null và holder vẫn chưa được khởi tạo.

~~~java
AtomicInteger attempts = new AtomicInteger();

LazyConstant<String> value = LazyConstant.of(() -> {
    attempts.incrementAndGet();
    return null;
});

boolean nullRejected = false;

try {
    value.get();
} catch (NullPointerException expected) {
    nullRejected = true;
}

check(nullRejected, "null phải bị từ chối");
check(!value.isInitialized(), "null không khởi tạo holder");
check(attempts.get() == 1,
        "Phép thử này chỉ gọi supplier một lần");
~~~

Nếu kết quả hợp lệ của nghiệp vụ có thể là “không có dữ liệu”, hãy lưu Optional thay vì trả null:

~~~java
LazyConstant<Optional<Customer>> customer =
        LazyConstant.of(() -> findCustomer()
                .map(Optional::of)
                .orElseGet(Optional::empty));
~~~

Không suy ra quy tắc retry sau null từ quy tắc retry khi computing function tự ném exception. Hãy xem null là kết quả không hợp lệ và kiểm tra riêng trên đúng bản JDK. Nếu kết quả hợp lệ của nghiệp vụ có thể là “không có dữ liệu”, hãy lưu Optional thay vì trả null. Khi đó, holder chứa một Optional không-null; Optional.empty() biểu diễn trường hợp không tìm thấy dữ liệu.

### Computing function gọi lại chính nó

Một lazy constant không được phép khởi tạo bằng cách gọi lại get() của chính nó trong computing function. Ví dụ:

~~~java
import java.lang.LazyConstant;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<LazyConstant<String>> reference =
        new AtomicReference<>();

LazyConstant<String> recursive = LazyConstant.of(
        () -> reference.get().get());

reference.set(recursive);

boolean recursionRejected = false;

try {
    recursive.get();
} catch (IllegalStateException expected) {
    recursionRejected = true;
}

check(recursionRejected,
        "Recursive initialization phải bị phát hiện");
check(!recursive.isInitialized(),
        "Holder không được khởi tạo khi recursion thất bại");
~~~

Cùng nguyên tắc áp dụng cho dependency cycle gián tiếp: A khởi tạo B, B lại yêu cầu A. Hãy thiết kế dependency graph một chiều hoặc tách phần khởi tạo dùng chung để tránh chu trình.

## 7. Đọc kết quả và xác định số lần tính giá trị

Một bộ kiểm thử nên ghi riêng ba loại số liệu:

| Số liệu | Ý nghĩa | Cách đo |
|---|---|---|
| Số lần gọi get() | Số yêu cầu đọc nội dung từ caller | Bộ đếm ở phía caller |
| Số lần chạy computing function | Số lần supplier thực sự được thực thi | AtomicInteger tăng ngay đầu supplier |
| Số lần khởi tạo thành công | Số lần holder chuyển từ chưa khởi tạo sang có nội dung | Kiểm tra kết quả thành công và trạng thái API JDK 26 |

Không dùng số lần gọi get() thay cho số lần chạy supplier. Mười thread có thể gọi get() nhưng chỉ một thread thực hiện supplier nếu phép tính thành công.

Bảng diễn giải kết quả điển hình trong JDK 26:

| Kịch bản | get() được gọi | Supplier được chạy | Kết quả cuối |
|---|---:|---:|---|
| Tạo holder, chưa gọi get() | 0 | 0 | Chưa khởi tạo |
| Một get() thành công | 1 | 1 | Đã khởi tạo |
| Gọi get() thêm nhiều lần sau thành công | Nhiều | Vẫn 1 | Trả cùng nội dung |
| Nhiều thread cạnh tranh, supplier thành công | Nhiều | 1 | Mọi thread nhận cùng nội dung |
| Supplier lỗi một lần, lần gọi sau thành công | Ít nhất 2 | 2 | Đã khởi tạo sau lần thử lại |
| Supplier trả null | 1 | 1 | Ném NullPointerException; không lưu nội dung null |
| Supplier luôn lỗi | Mỗi lần get() đều có thể kích hoạt thử lại | Tăng theo số lần thử | Vẫn chưa khởi tạo |

Các con số trong bảng là số lần supplier được gọi trong những tình huống minh họa, không phải số thread hoặc số request tối đa mà API giới hạn.

### Không dùng counter trong production để điều khiển logic

AtomicInteger trong bài chỉ phục vụ kiểm thử. Không nên để nghiệp vụ phụ thuộc vào bộ đếm số lần khởi tạo hoặc trạng thái isInitialized() để quyết định có được dùng nội dung hay không. Hãy gọi get() khi cần nội dung; chính API chịu trách nhiệm đồng bộ hóa và bảo đảm giá trị.

isInitialized() và orElse() trong JDK 26 hữu ích cho quan sát trạng thái và kiểm thử, nhưng chúng không thay thế get() khi ứng dụng thực sự cần nội dung. Đặc biệt, kiểm tra isInitialized() rồi mới gọi get() không tạo thành một thao tác nguyên tử duy nhất; trạng thái có thể thay đổi giữa hai lời gọi do thread khác khởi tạo holder.

## 8. Giới hạn và các tình huống cần kiểm thử bổ sung

**Supplier chạy trên thread gọi get().** LazyConstant không tự chuyển phép tính sang executor khác. Nếu supplier thực hiện I/O chậm hoặc chờ tài nguyên, thread gọi get() sẽ bị giữ trong thời gian đó.

**Các thread cạnh tranh phải chờ.** Trong lúc một thread đang tính toán, các thread khác gọi get() có thể bị chặn cho đến khi tính toán hoàn tất hoặc thất bại. Nếu supplier bị treo vô thời hạn, các caller khác cũng có thể chờ vô thời hạn. LazyConstant không cung cấp timeout hay cơ chế hủy phép tính.

**Interruption không hủy khởi tạo.** Việc thread chờ bị interrupt không tự hủy computing function. get() không ném InterruptedException chỉ vì thread bị interrupt và không xóa trạng thái interrupt. Nếu supplier tự gọi API interruptible, supplier cần xử lý interruption theo logic riêng.

**Nội dung được giữ mạnh.** Sau khi khởi tạo, holder giữ tham chiếu mạnh đến nội dung và không có thao tác reset. Nếu nội dung giữ nhiều tài nguyên hoặc object lớn, LazyConstant có thể làm chúng tiếp tục reachable trong suốt vòng đời holder. Không dùng nó cho cache cần eviction hoặc dữ liệu cần giải phóng tùy ý.

**Không đồng nghĩa object bất biến sâu.** LazyConstant chỉ cố định giá trị tham chiếu/nội dung đã thiết lập. Nếu object bên trong mutable, ứng dụng vẫn phải bảo vệ các thay đổi sau khởi tạo.

**Dependency cycle và class initialization.** Lazy constant trong static initializer có thể tương tác với thứ tự khởi tạo class. Chu trình khởi tạo giữa các class có thể gây lỗi initialization theo JLS. Kiểm thử cả đường khởi tạo trực tiếp lẫn dependency gián tiếp.

**Không dùng reflection để quan sát trạng thái nội bộ.** Chỉ dùng API công khai và bộ đếm trong computing function. Không dựa vào tên class implementation, monitor, field private hoặc stack trace nội bộ của JDK.

## 9. Khác biệt khi nâng cấp lên JDK 27

JDK 27 phát hành ngày 15/09/2026 và đưa Lazy Constants sang preview lần thứ ba theo JEP 531. API và cách xử lý thất bại thay đổi so với JDK 26. Đây là điểm bắt buộc kiểm tra khi chuyển môi trường.

| Nội dung | JDK 26 – JEP 526, Second Preview | JDK 27 – JEP 531, Third Preview |
|---|---|---|
| Trạng thái | Preview API | Preview API |
| Lỗi unchecked exception hoặc Error | Throwable ban đầu được truyền về caller; holder chưa khởi tạo; lần get() sau có thể thử lại | Holder chuyển sang error state; lần đầu ném NoSuchElementException với throwable gốc làm cause; lần sau tiếp tục ném NoSuchElementException và không chạy supplier lại |
| Supplier trả null | Ném NullPointerException; không lưu nội dung null | Chuyển sang error state; ném NoSuchElementException với NullPointerException làm cause |
| Supplier gọi đệ quy | Ném IllegalStateException; holder chưa khởi tạo | Chuyển sang error state; ném NoSuchElementException với IllegalStateException làm cause |
| isInitialized() | Có | Đã bị loại khỏi API |
| orElse(other) | Có, không kích hoạt khởi tạo | Đã bị loại khỏi API |
| get() sau lỗi | Có thể tính lại | Không tính lại sau khi đã chuyển sang error state |

Trong JDK 27, một unchecked exception hoặc Error không còn tạo cơ hội retry bằng cách gọi get() lần nữa. Lần đầu thất bại, caller nhận NoSuchElementException có cause là lỗi gốc. Những lần get() tiếp theo tiếp tục nhận NoSuchElementException nhưng không có cause và supplier không chạy lại.

Do đó, không mang nguyên bài test retry của JDK 26 sang JDK 27 rồi kỳ vọng cùng kết quả. Khi nâng cấp:

1. Đổi compiler và runtime sang JDK 27, bật preview của JDK 27.
2. Thay test mong đợi IllegalStateException/NullPointerException trực tiếp bằng kiểm tra NoSuchElementException và cause theo JDK 27.
3. Xác nhận supplier chỉ chạy một lần ngay cả khi lần đầu thất bại.
4. Bỏ các lời gọi isInitialized() và orElse() vì hai phương thức này không còn trong API JDK 27.
5. Đặt retry nghiệp vụ ở ngoài LazyConstant nếu hệ thống cần phục hồi sau lỗi tạm thời. Không cố tái sử dụng một holder đã chuyển sang error state.

Ví dụ khung kiểm thử lỗi trên JDK 27:

~~~java
import java.lang.LazyConstant;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger attempts = new AtomicInteger();

LazyConstant<String> value = LazyConstant.of(() -> {
    attempts.incrementAndGet();
    throw new IllegalStateException("temporary");
});

NoSuchElementException firstFailure = null;

try {
    value.get();
} catch (NoSuchElementException exception) {
    firstFailure = exception;
}

check(firstFailure != null, "Lần đầu phải có NoSuchElementException");
check(firstFailure.getCause() instanceof IllegalStateException,
        "Cause phải là lỗi ban đầu");

try {
    value.get();
    throw new AssertionError("Lần gọi sau phải tiếp tục thất bại");
} catch (NoSuchElementException expected) {
    check(expected.getCause() == null,
            "Lần gọi sau không có cause");
}

check(attempts.get() == 1,
        "Supplier không được chạy lại trong error state");
~~~

Đoạn mã này chỉ dành cho JDK 27 preview. Không ghép nó vào source set Java 26 nếu source set đó cần biên dịch theo JDK 26.

## 10. Bài thực hành tổng hợp

Thực hiện trên JDK 26 với preview và ghi lại số lần supplier được chạy:

1. Tạo holder chứa một cấu hình kết nối. Xác nhận tạo holder và gọi orElse() không chạy supplier.
2. Gọi get() lần đầu. Xác nhận supplier chạy đúng một lần và holder được khởi tạo.
3. Gọi get() thêm 100 lần. Xác nhận bộ đếm vẫn bằng 1 và mọi lần trả cùng object.
4. Chạy kiểm thử cạnh tranh với 8, 16 và 32 thread. Dùng latch giữ supplier đang chạy để các caller cùng tiến đến get().
5. Xác nhận tất cả Future nhận cùng một object và supplier chỉ chạy một lần trong lần khởi tạo thành công.
6. Tạo supplier ném IllegalStateException lần đầu, thành công lần thứ hai. Xác nhận exception đầu tiên được truyền về caller, trạng thái chưa khởi tạo và lần gọi sau thử lại.
7. Lặp lại với Error. Ghi nhận Error được truyền về caller và số lần supplier thực thi.
8. Tạo supplier trả null. Xác nhận NullPointerException, holder không chứa null và phân biệt trường hợp này với supplier tự ném exception.
9. Tạo dependency cycle để kiểm tra IllegalStateException do recursive initialization.
10. Thử interrupt một thread đang chờ computing function. Xác nhận interruption không tự hủy phép tính; kiểm tra trạng thái interrupt của thread theo cách không làm mất tín hiệu.
11. Chạy lại các test tương ứng trên JDK 27. Ghi rõ test nào phải thay đổi do error state và hai phương thức API đã bị loại bỏ.

**Tiêu chí hoàn thành:** tạo được phép thử cạnh tranh có điều phối; chứng minh một supplier thành công chỉ chạy một lần dù nhiều thread cùng gọi get(); phân biệt số lần gọi get() và số lần supplier thực thi; kiểm chứng exception, Error, null và recursion theo semantics JDK 26; giải thích được happens-before, safe publication và giới hạn khi supplier bị treo; nhận diện các thay đổi JDK 27 trước khi nâng cấp.

## 11. Tài liệu tham khảo chính thức

- [JEP 526: Lazy Constants (Second Preview)](https://openjdk.org/jeps/526) — mục tiêu và phạm vi preview trong JDK 26.
- [Java 26 LazyConstant API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html) — get(), isInitialized(), orElse(), thread safety và exception handling của JDK 26.
- [Java 26 Core Libraries: Lazy Constants](https://docs.oracle.com/en/java/javase/26/core/lazy-constants.html) — cách sử dụng, dependency graph và chu trình khởi tạo.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — trạng thái JEP 526 trong JDK 26.
- [JEP 531: Lazy Constants (Third Preview)](https://openjdk.org/jeps/531) — thay đổi của preview trong JDK 27.
- [Java 27 LazyConstant API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html) — error state, NoSuchElementException và API hiện hành trong JDK 27.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — xác nhận Lazy Constants là Third Preview trong JDK 27.

Dùng JDK 26 Javadoc để xác định kết quả của bài test JDK 26 và JDK 27 Javadoc để xác định kết quả sau nâng cấp. Lazy Constants vẫn là preview trong cả hai release; không coi API hoặc hành vi lỗi của một preview là cam kết tương thích cho release tiếp theo.

