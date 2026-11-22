# Lan truyền InterruptedException khi hợp đồng cho phép

## 1. Vì sao cần lan truyền tín hiệu ngắt?

Trong Java, **interruption** là một cơ chế để một thread thông báo cho thread khác rằng công việc hiện tại nên được dừng, hủy hoặc xem xét lại. Đây là **yêu cầu hợp tác**: gọi **Thread.interrupt()** không buộc JVM giết thread và không tự đảo ngược dữ liệu đã thay đổi.

Khi một thread đang chờ tại một phương thức có thể bị ngắt, ví dụ **Thread.sleep()**, **CountDownLatch.await()**, **BlockingQueue.take()**, **Future.get()** hoặc **Thread.join()**, phương thức đó có thể ném **InterruptedException**. Ngoại lệ này giúp code nhận biết rằng yêu cầu ngắt cần được xử lý thay vì tiếp tục đợi đến khi công việc hoàn tất.

Đối với một phương thức được phép khai báo **throws InterruptedException**, lựa chọn thường phù hợp nhất là **để exception lan truyền lên caller**. Caller ở cấp cao hơn có nhiều thông tin hơn để quyết định nên dừng cả nghiệp vụ, hủy công việc liên quan, thông báo trạng thái hay chuyển quyền xử lý cho tầng điều phối.

Ví dụ một phương thức service gọi repository có thao tác chờ:

~~~java
// Hai phương thức minh họa; không phải chương trình độc lập.
static String fetch() throws InterruptedException {
    return queue.take();
}

static String load() throws InterruptedException {
    return fetch();
}
~~~

Giả sử **queue** là một **BlockingQueue<String>** đã khai báo. Nếu thread đang đợi phần tử ở **queue.take()** bị interrupt, InterruptedException đi qua **fetch()** rồi đến **load()**; hai tầng không cần bắt rồi tiếp tục chạy như thể không có gì xảy ra.

Ý nghĩa của **lan truyền** ở đây là giữ nguyên tín hiệu kiểm soát vòng đời công việc. Đây không phải exception đại diện cho lỗi nghiệp vụ thông thường và cũng không mặc nhiên đồng nghĩa một task khác trong hệ thống đã bị hủy.

## 2. Hợp đồng throws InterruptedException

**InterruptedException** là checked exception thuộc **java.lang** và kế thừa **Exception**. Một phương thức gọi API có thể ném InterruptedException phải:

1. Khai báo **throws InterruptedException** và để lỗi lan truyền; hoặc
2. Bắt exception để xử lý theo một chính sách rõ ràng.

Nếu tầng hiện tại chỉ là một bước trung gian và có quyền khai báo checked exception, cách thứ nhất thường đơn giản, an toàn và thể hiện đúng hợp đồng.

~~~java
// Minh họa một chuỗi gọi hợp lệ theo cấu trúc Java.
static void lowLevel() throws InterruptedException {
    Thread.sleep(1_000);
}

static void middleLevel() throws InterruptedException {
    lowLevel();
}

static void higherLevel() throws InterruptedException {
    middleLevel();
}
~~~

Đoạn này là các phương thức độc lập về logic nhưng cần đặt trong một class để biên dịch. **higherLevel()** không cần tạo một exception mới; nó cho caller biết hoạt động có thể bị gián đoạn.

Một chữ ký **throws InterruptedException** là thông tin thiết kế API quan trọng:

- Caller biết đây là lời gọi có thể bị ngắt trong lúc chờ.
- Caller có thể chủ động quyết định việc thoát, cleanup hay tiếp tục ở ranh giới sở hữu công việc.
- Code review dễ phát hiện một tầng trung gian vô tình nuốt hoặc đổi nghĩa interrupt.
- Test có thể xác minh interruption đi xuyên qua các tầng.

Tuy nhiên, không nên khai báo throws một cách tùy tiện ở API không thật sự cần thiết. Chỉ chuyển tín hiệu này thành một phần của hợp đồng khi có thao tác interruptible hoặc có lý do giao tiếp phù hợp với caller.

## 3. Interrupt flag và exception liên quan nhau như thế nào?

Mỗi đối tượng **Thread** có trạng thái interrupt riêng. Một thread khác có thể gọi **target.interrupt()** để thiết lập yêu cầu ngắt. Điều gì xảy ra tiếp theo phụ thuộc mã và thao tác thread đang thực hiện:

- Nếu thread đang chờ ở một API interruptible, thao tác chờ có thể dừng và ném InterruptedException.
- Nếu thread đang chạy code tính toán thông thường, lời gọi interrupt chủ yếu thiết lập cờ; code phải kiểm tra cờ hoặc gặp API interruptible mới có phản ứng thích hợp.
- Nếu API không hỗ trợ interruption, interrupt có thể không dừng thao tác đó.

Hai cách kiểm tra cờ thường bị nhầm:

| API | Chức năng | Có xóa interrupt flag không? |
| --- | --- | --- |
| **Thread.currentThread().isInterrupted()** | Đọc trạng thái interrupt của thread hiện tại | Không |
| **someThread.isInterrupted()** | Đọc trạng thái interrupt của thread được tham chiếu | Không |
| **Thread.interrupted()** | Đọc trạng thái interrupt của **thread đang gọi** | **Có**, xóa cờ khi kiểm tra |
| **Thread.currentThread().interrupt()** | Đặt lại/yêu cầu interrupt trên thread hiện tại | Thiết lập cờ |

Nhiều API blocking theo hợp đồng JDK, bao gồm **CountDownLatch.await()**, khi phát hiện interruption và ném InterruptedException sẽ **xóa trạng thái interrupted** của thread trước khi ném. Bởi vậy, sau khi bắt InterruptedException, **isInterrupted()** có thể là false dù đã có yêu cầu ngắt hợp lệ.

Điểm quyết định chính sách:

- **Nếu có thể ném InterruptedException lên tầng gọi**, chỉ cần **throw** hoặc **throw e** là thường đủ để thông báo tín hiệu ngắt. Tầng gọi nhận exception có ý nghĩa; không bắt buộc phải tự đặt lại interrupt flag trong từng tầng trung gian.
- **Nếu không thể ném checked exception**, ví dụ trong **Runnable.run()**, code thường nên khôi phục interrupt flag bằng **Thread.currentThread().interrupt()** rồi kết thúc hoặc để ranh giới điều phối quyết định.
- **Nếu đang chuyển sang một kiểu exception khác**, phải xác định tầng gọi có còn nhận biết interruption không. Thường nên bảo tồn interrupt flag và cause khi không thể truyền trực tiếp InterruptedException.

Không có một quy tắc “luôn re-interrupt rồi luôn throw” cho mọi API. Nếu vừa khôi phục interrupt flag vừa tiếp tục gọi các phương thức blocking, chúng có thể ném InterruptedException ngay sau đó. Chính sách phải phù hợp với hợp đồng hiện tại và ranh giới sở hữu thread.

## 4. Ví dụ Java 17+: lan truyền qua các tầng, xử lý ở Runnable boundary

Chương trình sau mô phỏng ba tầng:

1. **repositoryWait** là tầng thấp dùng **CountDownLatch.await()**, có thể ném InterruptedException.
2. **serviceWait** cần một bước quan sát nhưng vẫn **throw failure** để truyền đúng exception lên trên.
3. **Runnable** là ranh giới cuối cùng; **run()** không khai báo checked InterruptedException nên nó bắt, khôi phục interrupt flag và kết thúc công việc.

Dùng hai latch để phối hợp giúp kết quả không phụ thuộc vào giả định thread chạy nhanh hay chậm. **gate** không bao giờ được mở; việc chờ chỉ có thể kết thúc ở ví dụ này bằng interruption.

Lưu vào file **InterruptPropagationDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class InterruptPropagationDemo {
    static void repositoryWait(CountDownLatch gate)
            throws InterruptedException {
        try {
            gate.await();
        } finally {
            System.out.println("Repository cleanup");
        }
    }

    static void serviceWait(CountDownLatch gate)
            throws InterruptedException {
        try {
            repositoryWait(gate);
        } catch (InterruptedException failure) {
            System.out.println("Service propagates interruption");
            throw failure;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                ready.countDown();
                serviceWait(gate);
                System.out.println("Unexpected completion");
            } catch (InterruptedException failure) {
                System.out.println("Boundary caught: InterruptedException");
                System.out.println("Flag in catch: "
                        + Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("Flag restored: "
                        + Thread.currentThread().isInterrupted());
            }
        }, "worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
        System.out.println("Worker finished: " + !worker.isAlive());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 InterruptPropagationDemo.java
java InterruptPropagationDemo
~~~

Kết quả stdout đã kiểm tra bằng cách biên dịch và chạy:

~~~text
Repository cleanup
Service propagates interruption
Boundary caught: InterruptedException
Flag in catch: false
Flag restored: true
Worker finished: true
~~~

### Diễn giải trình tự

**ready.countDown()** xác nhận worker đã bắt đầu. Sau khi main đi qua **ready.await()**, main gọi **worker.interrupt()**. Lúc này worker có thể đã ở trong **gate.await()** hoặc sắp gọi await; cả hai trường hợp đều khiến chờ trên gate phát hiện trạng thái interrupt và ném InterruptedException.

Trong **repositoryWait**, **finally** vẫn chạy và in **Repository cleanup**. Exception đang được ném tiếp, vì finally không tự thay thế nó bằng một exception khác.

Trong **serviceWait**, catch chỉ ghi dấu mốc và **throw failure**: cùng một instance InterruptedException tiếp tục truyền lên. Vì tầng service được khai báo **throws InterruptedException**, nó không cần che exception bằng RuntimeException và không cần khôi phục cờ tại đây.

**CountDownLatch.await()** xóa trạng thái interrupt khi ném exception, nên ở **Runnable** giá trị **isInterrupted()** được in là false. Vì **Runnable.run()** không được phép khai báo throws InterruptedException, worker khôi phục cờ rồi kết thúc nhánh catch. Main dùng **join()** để xác nhận thread đã kết thúc trước khi in dòng cuối.

Ví dụ minh họa hợp đồng này trong một đường chạy có điều khiển. Nó không có nghĩa mọi API đều xóa cờ khi ném mọi loại exception; phải dựa vào hợp đồng của từng phương thức.

## 5. Lan truyền nguyên trạng tốt hơn khi nào?

Trong một hệ thống nhiều lớp, tầng thấp thường không phải chủ sở hữu vòng đời toàn bộ công việc. Chẳng hạn:

~~~text
Controller / job coordinator
    |
    v
Application service
    |
    v
Repository / integration adapter
    |
    v
BlockingQueue.take() hoặc CountDownLatch.await()
~~~

Nếu tầng repository bắt InterruptedException rồi tiếp tục lặp vô hạn, tầng controller có thể không bao giờ xử lý được yêu cầu hủy request. Nếu tầng service tự chuyển mọi interruption thành lỗi dữ liệu, tầng coordinator dễ retry sai và gây tải không cần thiết.

Khi các chữ ký phương thức cho phép, hãy để **InterruptedException** truyền lên đến nơi có thể đưa ra quyết định về vòng đời tác vụ. Một tầng trung gian vẫn có thể catch để:

- Đảm bảo cleanup cục bộ.
- Ghi thông tin chẩn đoán thật sự cần thiết.
- Điều chỉnh dữ liệu tạm chưa công bố theo hợp đồng.
- Đính kèm ngữ cảnh mà không làm thay đổi bản chất tín hiệu ngắt.

Sau đó **ném lại đúng exception** nếu tầng trên vẫn được phép nhận InterruptedException.

Không nhất thiết phải catch chỉ để log rồi throw ở tất cả các tầng. Cách này có thể tạo log trùng lặp và không bổ sung ích lợi thực tế. Một phương thức chỉ cần:

~~~java
// Mã minh họa bên trong một class có biến queue thích hợp.
static String load(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

Chữ ký thể hiện đầy đủ hợp đồng gián đoạn; không cần catch thừa.

## 6. Không nuốt InterruptedException

Một lỗi thường gặp:

~~~java
// Phản mẫu minh họa.
try {
    blockingCall();
} catch (InterruptedException ignored) {
    // Tiếp tục xử lý như chưa từng có yêu cầu hủy.
}
doNextStep();
~~~

Đây là ví dụ minh họa trong phương thức lớn hơn. Nếu blockingCall dừng do interrupt, mã tiếp tục **doNextStep()** có thể làm các side effect mà bên điều phối đang yêu cầu dừng lại.

Một phản mẫu khác:

~~~java
// Phản mẫu minh họa: vòng lặp không có đường thoát.
while (true) {
    try {
        process(queue.take());
    } catch (InterruptedException ignored) {
        // Nuốt tín hiệu rồi quay lại take().
    }
}
~~~

Một API blocking thường xóa flag khi ném InterruptedException. Sau khi exception bị nuốt, vòng lặp có thể quay lại chờ vô thời hạn với cờ đã xóa. **Interrupt không còn khả năng điều phối việc thoát** nếu code liên tục bỏ qua nó.

Nếu API gọi cho phép:

~~~java
// Phương thức minh họa; queue là BlockingQueue<Task>.
static void runOne(BlockingQueue<Task> queue)
        throws InterruptedException {
    Task task = queue.take();
    task.execute();
}
~~~

Chỉ cần truyền InterruptedException từ **take()**. Đoạn code theo ngữ cảnh này giả sử đã có kiểu Task với phương thức execute; đây không phải chương trình chạy độc lập.

Nếu code không được phép khai báo checked exception và không có chính sách xử lý đầy đủ tại đây, cách thường dùng là khôi phục flag rồi ngừng:

~~~java
// Trong một Runnable hoặc callback không khai báo InterruptedException.
try {
    blockingCall();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Việc **return** ở đây là kết thúc tác vụ hiện tại sau khi đã khôi phục cờ, khác với **return trong finally** có thể che lỗi. Nếu còn tài nguyên cần cleanup, cleanup phải được tổ chức để vẫn chạy trước khi tác vụ kết thúc.

## 7. Vì sao không cần re-interrupt ở từng tầng khi đang throw?

Xét chuỗi sau:

~~~java
// Minh họa phương thức có hợp đồng throws InterruptedException.
static void service() throws InterruptedException {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw e;
    }
}
~~~

Đoạn này không nhất thiết sai trong mọi bối cảnh, nhưng bước **interrupt()** ngay trước **throw e** thường **không cần thiết** nếu mục tiêu duy nhất là báo interruption cho caller. Bản thân exception đã truyền tín hiệu. Khi tầng trên nhận lỗi và dự định thực hiện cleanup có thao tác blocking, interrupt flag được đặt lại sớm có thể khiến thao tác cleanup đó bị ngắt ngay. Hợp đồng tầng trên mới quyết định thời điểm xử lý flag.

Một cách đơn giản hơn:

~~~java
// Minh họa phương thức có hợp đồng throws InterruptedException.
static void service() throws InterruptedException {
    Thread.sleep(10_000);
}
~~~

Nếu cần catch để dọn dẹp, vẫn có thể giữ nguyên exception:

~~~java
// Minh họa; releaseLocalState() phải theo hợp đồng riêng.
try {
    blockingOperation();
} catch (InterruptedException e) {
    releaseLocalState();
    throw e;
}
~~~

Lưu ý: nếu **releaseLocalState()** cũng ném exception, nó có thể che khuất InterruptedException. Với cleanup có thể ném lỗi, cần dùng cơ chế bảo toàn primary exception phù hợp, ví dụ **try-with-resources** cho AutoCloseable hoặc suppressed exceptions khi xử lý thủ công. Không chỉ quan tâm việc ghi **throw e** mà bỏ qua ảnh hưởng của đường cleanup.

## 8. Giữ đúng kiểu InterruptedException và stack trace

Khi lan truyền:

- **throw e** ném lại chính đối tượng vừa bắt và giữ những thông tin có trên exception đó.
- **throws InterruptedException** trên chữ ký cho caller biết loại checked exception có thể xuất hiện.
- Không tạo **new InterruptedException(e.getMessage())** nếu không có lý do đặc biệt: cách này tạo đối tượng mới và không tự bảo toàn đầy đủ cause/suppressed/stack trace của exception ban đầu.
- Không bao bọc thành một RuntimeException chung khi chữ ký có thể truyền nguyên trạng; caller có thể không còn catch được InterruptedException như mong đợi.

Trong một service interface mà nhiều implementation cần hỗ trợ gián đoạn, việc đưa InterruptedException vào chữ ký có thể là quyết định hợp lý. Nếu đó là API công khai không cho phép checked exception, cần chính sách chuyển đổi đã được tài liệu hóa; tránh che interruption bằng thông báo nghiệp vụ không liên quan.

### Nếu muốn thêm ngữ cảnh

Không phải lúc nào cũng cần tạo một exception mới. Có thể ghi context ở một ranh giới điều phối, giữ Throwable nguyên vẹn và để tầng trên quyết định. Nếu API bắt buộc wrap, cần:

1. Khôi phục interrupt flag nếu không còn truyền trực tiếp InterruptedException theo hợp đồng.
2. Bảo tồn original dưới dạng **cause** khi kiểu wrapper hỗ trợ.
3. Bảo đảm tầng gọi hiểu wrapper đó biểu diễn sự gián đoạn, không phải lỗi nghiệp vụ thông thường.
4. Tránh retry tự động các thao tác không idempotent.

Ví dụ chuyển đổi trong callback không khai báo checked exception:

~~~java
// Mã minh họa trong callback không khai báo checked exceptions.
try {
    blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", e);
}
~~~

Đây là một chính sách API có thể dùng trong một số trường hợp, nhưng không có nghĩa **IllegalStateException** là kiểu cancellation tiêu chuẩn hay mọi callback đều nên xử lý như vậy. Nếu API cung cấp một kiểu exception/cancellation thích hợp hơn, ưu tiên hợp đồng của API đó. Có callback nên kết thúc bình thường sau khi ghi trạng thái hủy thay vì ném unchecked exception.

## 9. Runnable khác Callable về hợp đồng exception

**Runnable.run()** không khai báo checked exception. Vì thế một method reference/lambda Runnable không thể đơn giản gọi API throws InterruptedException rồi để exception đó đi xuyên qua **run()** nếu không có catch hoặc chuyển đổi phù hợp.

~~~java
// Minh họa Runnable trong một phương thức.
Runnable task = () -> {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
};
~~~

Trong khi đó, **Callable<V>.call()** được khai báo **throws Exception**, nên một Callable có thể để InterruptedException truyền ra:

~~~java
// Minh họa Callable theo ngữ cảnh.
Callable<String> task = () -> {
    Thread.sleep(10_000);
    return "done";
};
~~~

Tuy nhiên, khi gửi Callable qua **ExecutorService.submit()**, caller bên ngoài thường không nhận InterruptedException do *worker ném* theo kiểu trực tiếp khi gọi **Future.get()**. Nếu task thất bại với InterruptedException và Future chưa canceled, **Future.get()** thường ném **ExecutionException** có **getCause()** là InterruptedException.

Cần phân biệt:

| Tình huống | Tín hiệu người gọi Future.get() nhận |
| --- | --- |
| **Chính thread đang gọi get()** bị interrupt trong lúc chờ | **InterruptedException** trực tiếp |
| **Callable của worker** ném InterruptedException và Future hoàn tất bất thường | **ExecutionException**, cause là InterruptedException |
| Future đã chuyển sang trạng thái canceled | **CancellationException** |
| Một lần gọi get(timeout) hết hạn chờ | **TimeoutException** |

Vì vậy, không được kết luận mọi InterruptedException quan sát ở code bất đồng bộ đều liên quan cùng một thread. Có hai chủ thể khác nhau: **caller đang đợi** và **worker đang thực thi**.

### CompletableFuture

**CompletableFuture.supplyAsync** dùng **Supplier<T>**, mà phương thức **get()** của Supplier không khai báo throws InterruptedException. Do đó lambda supplier phải catch hoặc dùng một adapter theo chính sách hủy. **CompletableFuture.get()** và **join()** cũng có hợp đồng chờ/exception khác nhau: get khai báo InterruptedException, còn join không khai báo checked InterruptedException.

Đừng giả định rằng **CompletableFuture.cancel(true)** bắt buộc interrupt supplier đang chạy. CompletableFuture sử dụng trạng thái completion riêng và tham số **mayInterruptIfRunning** không điều khiển computation theo cùng cách FutureTask thông thường. Nếu cần ngắt công việc thật sự, quản lý riêng Future/task bên dưới hoặc token hủy phù hợp.

## 10. Không đồng nhất InterruptedException với CancellationException

**InterruptedException** nói rằng thao tác chờ có thể ngắt của thread hiện tại đã bị gián đoạn. **CancellationException** mô tả trạng thái hủy của đối tượng Future hoặc kết quả bất đồng bộ. Một yêu cầu cancel(true) đối với Future có thể khiến cơ chế executor gửi interrupt cho worker, nhưng hai ngoại lệ vẫn xuất hiện ở những vị trí và ý nghĩa khác nhau.

Một Future có thể đã canceled và **get()** ném CancellationException dù worker chưa xử lý interrupt xong. Cũng có thể thread bị interrupt khi gọi Future.get() trong lúc task vẫn tiếp tục làm việc, khiến caller nhận InterruptedException mà Future chưa canceled.

**TimeoutException** lại mô tả một lần chờ có timeout đã hết hạn; nó không tự interrupt caller hoặc cancel Future. Chỉ ứng dụng mới quyết định tiếp tục chờ, trả fallback, gửi yêu cầu hủy hay kết thúc request.

Khi truyền InterruptedException lên trên, caller cần đánh giá có phải hủy những task con liên quan không. Đây là chính sách của nhóm công việc, không phải một tác dụng phụ tự động của từ khóa **throws**.

## 11. Cleanup khi lan truyền interruption

Khi interruption xảy ra giữa một thao tác có tài nguyên, code vẫn phải bảo đảm cleanup thích hợp. Cấu trúc **try/finally** cho phép cleanup chạy khi exception truyền lên:

~~~java
// Minh họa: lock được khai báo và có thể lấy bằng lockInterruptibly().
lock.lockInterruptibly();
try {
    blockingOperation();
} finally {
    lock.unlock();
}
~~~

Điểm quan trọng là **lock.lockInterruptibly()** nằm trước khối try. Nếu acquire bị interrupt và ném InterruptedException thì thread chưa sở hữu lock theo đường thành công, và code không được gọi unlock như thể đã giữ lock. Sau khi acquire thành công, finally chịu trách nhiệm unlock khi thân try kết thúc hoặc ném lỗi.

Một phản mẫu dễ sai:

~~~java
// Phản mẫu minh họa, không dùng trong chương trình thật.
try {
    lock.lockInterruptibly();
    blockingOperation();
} finally {
    lock.unlock(); // Có thể unlock khi chưa hề lock thành công.
}
~~~

Nếu lockInterruptibly thất bại trước khi lấy khóa, unlock có thể ném **IllegalMonitorStateException**, che lỗi InterruptedException ban đầu. Hãy đặt phạm vi cleanup sau khi tài nguyên/khóa đã được nhận thành công, hoặc theo dõi rõ việc acquire có thành công không.

### Cleanup có thể tự thất bại

Nếu xử lý chính ném InterruptedException và close/rollback trong finally lại ném exception mới, exception cleanup có thể che khuất tín hiệu interrupt. Với tài nguyên **AutoCloseable**, ưu tiên **try-with-resources**, vì lỗi close sẽ được lưu dưới dạng **suppressed** khi thân try đã ném primary exception.

~~~java
// Minh họa: resource là AutoCloseable.
try (var resource = openResource()) {
    resource.blockingAction(); // Có thể throws InterruptedException.
}
~~~

Đoạn này cần nằm trong bối cảnh API thích hợp; nó chỉ là mã minh họa. Để giữ InterruptedException truyền nguyên trạng, caller hoặc phương thức bao cần chấp nhận loại checked exception tương ứng, cùng những checked exceptions khác mà close có thể ném theo hợp đồng của resource.

**Cleanup không phải rollback tự động.** Giải phóng khóa không đảo ngược object mutable đã sửa; đóng stream không xóa byte đã ghi; hủy chờ không chứng minh request từ xa chưa tạo side effect. Khi interruption xảy ra, các quy tắc bảo toàn trạng thái và giao dịch vẫn cần được thiết kế riêng.

## 12. Giữ trạng thái nhất quán khi ngắt giữa nhiều bước

Việc truyền InterruptedException đúng loại chỉ giải quyết luồng điều khiển và thông tin hủy. Nếu code đã sửa dữ liệu trước khi gọi một blocking operation, trạng thái có thể thay đổi một phần:

~~~java
// Phản mẫu minh họa: entries là mutable list đã được công bố.
entries.add(item);
remoteGate.await(); // Có thể ném InterruptedException.
commitOtherFields();
~~~

Nếu remoteGate.await bị ngắt, danh sách đã thêm item nhưng phần cập nhật khác chưa hoàn tất. Để bảo toàn trạng thái mạnh, có thể:

1. Kiểm tra điều kiện và chuẩn bị dữ liệu mới trên biến cục bộ/snapshot riêng.
2. Thực hiện các thao tác chờ hoặc tính toán có thể ném InterruptedException trước khi công bố.
3. Chỉ commit khi mọi điều kiện đã thỏa và vẫn được phép công bố kết quả.
4. Nếu thao tác đã gửi side effect bên ngoài, áp dụng transaction, idempotency hoặc quy trình bù trừ phù hợp.

Mã minh họa:

~~~java
// Minh họa phương thức theo ngữ cảnh; không phải chương trình độc lập.
Snapshot candidate = prepareCandidate(current);
remoteGate.await();  // Nếu bị ngắt, current vẫn giữ nguyên.
current = candidate;  // Commit sau khi chuẩn bị thành công.
~~~

Điều này chỉ cung cấp đảm bảo trong phạm vi trạng thái mà **current** thật sự sở hữu và kiểm soát. Nếu chuẩn bị candidate còn sửa object mutable dùng chung hoặc remoteGate tạo side effect bên ngoài, phép gán cuối không biến toàn bộ hệ thống thành một giao dịch nguyên tử.

Ngoài ra, giữa lần kiểm tra cờ interrupt và commit có thể có race: yêu cầu interrupt có thể đến ngay sau khi kiểm tra. Hệ thống cần xác định điểm nào được xem là đã commit và hứa hẹn cancellation đến mức nào; không thể tùy tiện cam kết rằng *mọi yêu cầu interrupt đến bất kỳ thời điểm nào* đều ngăn mọi side effect.

## 13. Gián đoạn trong vòng lặp làm việc

Một worker chạy nhiều đơn vị công việc nên có đường thoát rõ:

~~~java
// Minh họa logic của worker, không phải chương trình độc lập.
static void consume(BlockingQueue<Job> queue)
        throws InterruptedException {
    while (true) {
        Job job = queue.take();
        job.process();
    }
}
~~~

Ở đây **queue.take()** có thể ném InterruptedException. Nếu tầng gọi cho phép, exception sẽ thoát khỏi **consume()**, từ đó vòng lặp chấm dứt. Không cần bắt InterruptedException rồi **continue**: làm vậy có thể khiến worker phớt lờ yêu cầu ngắt.

Nhưng nếu **job.process()** là CPU-bound kéo dài hoặc dùng I/O không nhận interrupt, tín hiệu ngắt có thể không được xử lý trong khoảng thời gian đó. Có thể thiết kế các điểm kiểm tra:

~~~java
// Minh họa theo ngữ cảnh; không phải chương trình độc lập.
while (!Thread.currentThread().isInterrupted()) {
    doSmallUnitOfWork();
}
~~~

Điều kiện **isInterrupted()** chỉ kiểm tra flag; nó không tự ném InterruptedException. Nếu hợp đồng worker muốn thông báo ngắt qua checked exception, cần lựa chọn một điểm chuyển tín hiệu phù hợp hoặc sử dụng các API interruptible; đừng tự tạo InterruptedException tùy tiện khi chưa xác định semantics.

### Khi cần dừng vòng lặp nhưng cleanup có tính bắt buộc

Một worker có thể có finally để trả connection/lock sau khi vòng lặp kết thúc. Khi interruption ném qua các tầng, finally chạy trên đường thoát trong điều kiện thực thi thông thường. Nếu cleanup cần thực hiện thao tác blocking mới, phải xem xét flag đã được xóa hay chưa và cleanup có chính sách timeout riêng không. Tránh chặn vô hạn trong cleanup của đường hủy.

## 14. Interruption trong ExecutorService

Khi một task được submit vào ExecutorService:

- **Future.cancel(true)** có thể đề nghị interrupt task đang chạy nếu executor và task cho phép.
- **ExecutorService.shutdownNow()** cố ngắt các worker đang thực thi, nhưng không cam kết mọi task dừng ngay lập tức.
- **ExecutorService.shutdown()** không tự gửi interrupt tới tất cả task đã được nhận như shutdownNow.
- **awaitTermination(timeout, unit)** là lời gọi có thể ném InterruptedException trên thread đang đợi executor kết thúc.

Nếu thread quản lý executor bị interrupt trong khi đợi shutdown, policy phù hợp có thể là ngừng đợi, yêu cầu shutdownNow khi thật sự sở hữu executor, sau đó khôi phục flag hoặc ném tiếp InterruptedException. Không được tắt một executor dùng chung chỉ vì caller của một request bị interrupt khi tầng đó không sở hữu vòng đời executor.

Ví dụ minh họa về một ranh giới quản lý executor đã sở hữu:

~~~java
// Mã minh họa, executor thuộc quyền sở hữu của phạm vi này.
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây là chính sách dành cho một ngữ cảnh **không tiếp tục ném InterruptedException** và có quyền yêu cầu dừng executor. Nếu phương thức cho phép **throws InterruptedException**, có thể thay ranh giới bằng cách ném tiếp sau cleanup phù hợp. Không áp dụng máy móc vào thread pool dùng chung của server.

## 15. API không cho phép checked exception: chuyển đổi có trách nhiệm

Một số interface không khai báo checked exception, ví dụ **Runnable**, **Supplier**, một số callback hoặc phương thức override bị ràng buộc chữ ký. Không thể thêm **throws InterruptedException** vào một phương thức override nếu interface không cho phép.

Khi đó các lựa chọn thường gặp gồm:

- **Khôi phục interrupt flag và kết thúc công việc** khi interruption mang nghĩa yêu cầu dừng.
- **Chuyển thành exception unchecked có cause rõ ràng** khi framework cần đường báo lỗi bất thường và hợp đồng cho phép.
- **Đưa trạng thái canceled vào kết quả nghiệp vụ** nếu API được thiết kế để đại diện cancellation bằng một trạng thái riêng.
- **Dùng wrapper/adaptor bên ngoài** để đặt thao tác blocking vào giao diện có thể khai báo checked exception, ví dụ Callable khi thích hợp.

Không có một lựa chọn đúng tuyệt đối cho mọi callback. Tuy nhiên, **catch và bỏ qua** thường là sai vì làm tín hiệu ngắt biến mất.

Khi chuyển thành unchecked exception, không dùng một exception mơ hồ rồi để hệ thống retry vô điều kiện. Caller hoặc framework cần nhận biết lý do là interrupt/cancellation để quyết định vận hành phù hợp. Và việc đặt lại interrupt flag phải xét hợp đồng thread pool; không thực hiện hoạt động blocking tiếp theo như thể cờ đã được xóa.

## 16. Cách kiểm thử việc lan truyền InterruptedException

Một kiểm thử tốt cần kiểm tra cả **đường truyền exception** và **hành vi của thread sở hữu tác vụ**. Không nên chỉ gọi Thread.sleep với con số đoán trước rồi hy vọng một thread đã vào đúng vị trí blocking.

Ưu tiên dùng **CountDownLatch**, barrier hoặc công cụ đồng bộ để kiểm soát thời điểm:

1. Tạo latch **ready** cho biết thread đã bắt đầu.
2. Giữ một latch **gate** chưa mở để bảo đảm thao tác chờ chưa thể thành công.
3. Khi ready được phát tín hiệu, gọi **interrupt()** lên đúng thread đang kiểm thử.
4. Cho exception truyền qua phương thức tầng thấp và service bằng **throws InterruptedException**.
5. Tại boundary không khai báo checked exception, ghi nhận exception, khôi phục flag theo hợp đồng và thoát.
6. **join()** thread để xác minh không còn chạy; nếu là test production, cần timeout an toàn để tránh treo bộ test khi mã có lỗi.
7. Assert không có side effect sau interruption, cleanup bắt buộc đã chạy và dữ liệu chỉ thay đổi trong phạm vi đã cam kết.

Ở chương trình runnable, latch ready/gate loại bỏ sự phụ thuộc vào scheduler: interrupt xảy ra trước hay trong lời gọi await đều dẫn đến InterruptedException trên worker. Dòng **Repository cleanup** xác nhận finally đã chạy; dòng **Service propagates interruption** cho thấy tầng service ném tiếp; hai dòng **Flag** thể hiện trạng thái khi bắt và sau khi khôi phục.

### Các test case cần có

| Trường hợp | Kỳ vọng |
| --- | --- |
| Tầng thấp bị interrupt khi await | InterruptedException được ném |
| Tầng giữa khai báo throws và không nuốt | Caller nhận được InterruptedException |
| Tầng giữa catch rồi throw e | Caller vẫn nhận chính exception gốc |
| Tầng giữa catch rồi continue | Test phát hiện task không dừng theo hợp đồng |
| Runnable boundary không thể throws | Flag được khôi phục nếu policy chọn re-interrupt; task kết thúc |
| Callable worker ném InterruptedException | Future.get thường ném ExecutionException có cause là InterruptedException |
| Caller bị interrupt khi Future.get | Caller nhận InterruptedException trực tiếp |
| Cleanup trong finally chạy | Resource được dọn theo hợp đồng |
| Cleanup cũng ném lỗi | Primary không bị che khuất; suppressed phù hợp |
| Interrupt gần điểm commit | Ứng dụng giữ đúng semantics về thời điểm commit và side effect |

Nếu đang dùng unit test framework, có thể kiểm tra exception identity để phát hiện một tầng vô ý tạo exception mới. Trong bài test tích hợp, cần kiểm tra trạng thái tài nguyên và những tác dụng phụ thực sự, không chỉ assert kiểu Throwable.

## 17. Lỗi phổ biến và cách sửa

**Nuốt InterruptedException rồi tiếp tục.** Đây là lỗi cốt lõi: yêu cầu hủy không còn được phản ánh và task có thể thực hiện thêm side effect. Nếu được phép, khai báo throws và ném tiếp; nếu không được phép, dùng chính sách khôi phục flag/kết thúc phù hợp.

**Tự đặt lại interrupt flag ở mọi tầng dù đều throw.** Thường không cần khi caller đã nhận đúng InterruptedException. Hãy để ranh giới sở hữu công việc quyết định cách xử lý flag.

**Nhầm isInterrupted với Thread.interrupted.** Phương thức static Thread.interrupted kiểm tra và xóa cờ của thread hiện tại; dùng nó để “chỉ xem thử” có thể vô tình tiêu thụ tín hiệu.

**Chuyển interruption thành lỗi nghiệp vụ chung không có cause.** Caller mất khả năng phân biệt dừng tác vụ với lỗi xử lý dữ liệu. Nếu phải wrap, giữ cause và policy cờ ngắt.

**Tưởng Future.get ném InterruptedException nghĩa worker bị interrupt.** Đó có thể chỉ là thread caller đang chờ bị interrupt. Lỗi worker thường được chuyển qua ExecutionException khi quan sát Future chưa canceled.

**Dùng cancellation của CompletableFuture để khẳng định supplier dừng.** Trạng thái future và việc worker thực thi dừng là hai khái niệm khác nhau; cần cơ chế hủy cụ thể.

**Gọi unlock khi lockInterruptibly chưa acquire thành công.** Nếu acquire bị interrupt, unlock sai tạo IllegalMonitorStateException và có thể che lỗi gốc. Đặt try/finally sau khi lấy lock thành công.

**Để cleanup ném lỗi làm mất InterruptedException.** Nếu tài nguyên AutoCloseable, ưu tiên try-with-resources; nếu cleanup thủ công, giữ primary và suppressed.

**Cho rằng interruption rollback dữ liệu.** Interrupt chỉ là tín hiệu; các side effect trong RAM, file, database hay network cần chiến lược bảo toàn trạng thái riêng.

**Dựa vào Thread.sleep để tạo test race.** Scheduler có thể thay đổi. Dùng latch/barrier để kiểm soát điều kiện chờ và kiểm tra các kết quả được phép bởi hợp đồng.

## 18. Bảng kiểm khi viết phương thức có thể bị ngắt

Trước khi hoàn thiện một đoạn Java blocking hoặc chuỗi API có cancellation, tự hỏi:

1. Phương thức này có được phép khai báo **throws InterruptedException** không?
2. Tầng hiện tại có đủ quyền quyết định hủy tác vụ, hay nên để exception truyền lên?
3. Nếu bắt exception, có thật sự bổ sung xử lý hợp lệ trước khi **throw e** không?
4. Có catch nào nuốt interrupt, tiếp tục vòng lặp hoặc retry tự động không?
5. Khi một API blocking ném InterruptedException, nó có xóa cờ theo hợp đồng không?
6. Nếu không thể ném checked exception, boundary sẽ khôi phục flag, trả trạng thái hủy hay chuyển thành một exception khác như thế nào?
7. Đã phân biệt worker bị interrupt với thread caller của Future.get bị interrupt chưa?
8. Có cleanup nào ném exception khác và che mất lỗi interrupt không?
9. Nếu interruption xảy ra sau side effect, trạng thái có còn nhất quán và đã có cơ chế rollback/compensation cần thiết chưa?
10. Các test có kích hoạt interrupt tại đúng vị trí chờ, xác minh đường truyền exception và việc worker thoát không?

**Kết luận:** Khi chữ ký API cho phép, **lan truyền InterruptedException nguyên trạng** là một cách giữ đúng tín hiệu yêu cầu dừng và chuyển quyết định vòng đời công việc đến tầng có trách nhiệm. Không cần bắt rồi khôi phục cờ ở mọi tầng trung gian. Ở những ranh giới không được ném checked exception, phải có chính sách rõ ràng để bảo toàn ý nghĩa interruption, dọn dẹp tài nguyên và kết thúc an toàn. Interruption là tín hiệu điều phối, còn việc bảo toàn trạng thái và side effect luôn cần được thiết kế, kiểm chứng riêng.
