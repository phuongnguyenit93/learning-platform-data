# Kiểm tra tương thích với kiểm thử, đo độ bao phủ và gỡ lỗi trong AOP

Aspect-oriented programming (AOP) đưa các mối quan tâm xuyên suốt như kiểm soát truy cập, audit, đo thời gian, quản lý tài nguyên và xử lý lỗi vào những điểm thực thi (*join point*). Vì phần xử lý này có thể xuất hiện ở lớp proxy, chuỗi interceptor hoặc mã bytecode đã được biến đổi (*weaving*), một phép kiểm thử “nghiệp vụ trả đúng kết quả” **chưa đủ** để chứng minh advice được áp dụng chính xác. Ngược lại, việc công cụ đo *code coverage* báo 100% trên phương thức đích cũng không có nghĩa mọi điểm cần chặn đã được chặn.

Bài này cung cấp cách kiểm tra tương thích AOP với bộ kiểm thử, công cụ đo độ bao phủ và trình gỡ lỗi; đồng thời chỉ ra cách xác nhận **hành vi của advice, phạm vi pointcut và kết quả sau khi instrument** ở cả môi trường kiểm thử lẫn bản triển khai thực tế. Phạm vi là AOP nói chung, với các cơ chế proxy và weaving phổ biến ở mức khái niệm.

## 1. Ba câu hỏi phải kiểm chứng độc lập

1. **Chức năng còn đúng không?** Cùng yêu cầu nghiệp vụ phải giữ đúng kết quả, tác dụng phụ được phép, ngoại lệ, thứ tự thực hiện và ràng buộc dữ liệu.
2. **Advice có chạy đúng chỗ và đúng số lần không?** Pointcut chọn đúng join point; advice chạy khi bắt buộc và không chạy ở ngoài phạm vi; đường lỗi và lời gọi lồng nhau được xét đúng.
3. **Bằng chứng đo và gỡ lỗi có đáng tin không?** Công cụ coverage có nhìn đúng mã được chạy không, breakpoint có khớp vị trí bytecode không, stack trace có phản ánh lớp trung gian và thứ tự biến đổi hay không?

Ba câu hỏi này liên quan nhau nhưng không thay thế nhau. Ví dụ một hàm `transfer()` trả đúng số tiền có thể vẫn thiếu advice audit trên một đường gọi nội bộ. Test nghiệp vụ thành công sẽ không tự phát hiện lỗi đó nếu không khẳng định sự kiện audit phải được ghi.

### 1.1. Những thành phần ảnh hưởng đến kiểm thử

| Thành phần | Điều cần quan sát | Sai lệch thường gặp |
|---|---|---|
| Join point | Vị trí lời gọi hoặc thực thi thật sự | Nhầm caller với callee; bỏ qua đường gọi nội bộ |
| Pointcut | Điều kiện chọn điểm chặn | Quá rộng, quá hẹp, sai overload, sai điều kiện động |
| Advice | Before, after, after throwing, around | Chạy thiếu hoặc thừa; thay đổi kết quả/ngoại lệ |
| Proxy / interceptor chain | Đường dispatch và thứ tự mắt xích | Test gọi thẳng target nên không chạy advice |
| Weaving | Mã được chèn ở compile/load time | Bản test và bản chạy dùng class khác cách biến đổi |
| Instrumentation của coverage | Bộ đếm nhánh/dòng lệnh được chèn vào mã | Biến đổi bytecode không khớp, bỏ sót mã sinh |
| Debug metadata | Line number, method name, source mapping | Breakpoint lệch, stack frame do mã sinh tạo ra |
| Class loader / runtime agent | Class thực tế được nạp và biến đổi | Agent không chạy, thứ tự biến đổi khác môi trường |

Không phải mọi hệ thống AOP đều dùng proxy hoặc reflection. Một số công cụ biến đổi bytecode để advice thực thi ngay tại điểm được chọn; bởi vậy cách kiểm thử phải bám sát **cơ chế đang chạy thật**, không suy diễn từ một sơ đồ chung.

## 2. Kiểm thử ở đúng ranh giới can thiệp

### 2.1. Test phương thức đích và test lời gọi qua AOP là hai phép thử khác nhau

Giả sử một đối tượng `Ledger` thực thi `debit()`. Có thể có hai đường gọi:

```text
Unit test trực tiếp
    ↓
Ledger.debit()
    ↓
Kết quả nghiệp vụ

Integration test đi qua AOP
    ↓
Proxy / mã đã weave
    ↓
Advice kiểm tra chính sách
    ↓
Ledger.debit()
    ↓
Advice sau thực thi / khi lỗi
    ↓
Kết quả nghiệp vụ + bằng chứng advice
```

Khi dùng proxy, test chỉ khởi tạo `new Ledger()` và gọi trực tiếp có thể bỏ qua cơ chế chặn. Test này vẫn hữu ích để kiểm chứng logic thuần túy, nhưng **không xác minh việc proxy đã được gắn vào hệ thống**. Với weaving, đối tượng tạo bằng `new` có thể mang mã đã chèn nếu class được nạp bằng đường weaving tương ứng; phải xác minh cách nạp class và classpath thay vì giả định.

Một kế hoạch kiểm thử tốt giữ cả hai loại:

- **Kiểm thử logic nghiệp vụ:** ngắn, cô lập, dễ chẩn đoán; không nhất thiết cần khởi chạy hạ tầng AOP.
- **Kiểm thử hợp đồng advice:** kiểm tra logic advice với ngữ cảnh giả lập/harness tối thiểu; chỉ phù hợp khi advice không phụ thuộc những đặc tính runtime chưa được giả lập.
- **Kiểm thử tích hợp AOP:** lấy đối tượng qua đúng đường được instrument hoặc kích hoạt weaving thật; xác minh pointcut, dispatch, thứ tự advice và đường lỗi.
- **Kiểm thử end-to-end hoặc tải:** xác minh chuỗi hành vi trên các biên thực tế, tính tương thích khi đóng gói/chạy và overhead đo được ở tải đại diện.

### 2.2. Test double, mock và spy có thể thay đổi đường gọi

Test double giúp cách ly phụ thuộc nhưng cũng có thể làm biến mất hoặc đổi thứ tự AOP:

- Mock của **target** đặt phía sau proxy: có thể kiểm tra advice rồi xác nhận target được gọi.
- Mock của **đối tượng proxy** đưa thẳng cho caller: có thể thay thế luôn lớp interception; khi ấy test không chứng minh advice chạy.
- Spy hoặc subclass có thể ảnh hưởng thứ tự override/dispatch; các điểm chặn liên quan `final`, `private`, default method và bridge method phụ thuộc kỹ thuật instrument.
- Callback giả lập có thể không tái hiện đúng thread, class loader, exception wrapper hoặc lifecycle context.

Khi cần kiểm chứng advice thật, phải chỉ rõ **đối tượng nào được instrument, object nào được thay bằng test double và lời gọi đi qua tuyến nào**. Không coi mọi mock-based test là kiểm thử tích hợp AOP.

### 2.3. Ma trận hành vi tối thiểu

| Tình huống | Kỳ vọng cần assert |
|---|---|
| Lời gọi khớp pointcut | Advice được chạy; target chạy theo hợp đồng |
| Lời gọi không khớp | Advice không chạy; nghiệp vụ không đổi |
| Phương thức overload | Chọn đúng chữ ký theo chính sách |
| Điều kiện động đúng/sai | Chặn theo dữ liệu thực tế ở từng invocation |
| Target trả kết quả bình thường | After returning/around giữ hoặc biến đổi kết quả đúng quy tắc |
| Target ném ngoại lệ | After throwing/finally xử lý đúng; không vô tình nuốt lỗi |
| Advice ném ngoại lệ | Tác động lên target và caller đúng hợp đồng |
| Around bỏ qua `proceed()` | Target không chạy khi được phép short-circuit |
| Around gọi `proceed()` nhiều lần | Đếm đúng lần gọi đích, side effect và cơ chế retry |
| Nhiều advice | Đúng thứ tự before, after, finally, exception path |
| Gọi trong cùng đối tượng | Xác nhận có hoặc không bị chặn tùy cơ chế |
| Async/concurrent | Ngữ cảnh được truyền, cô lập và dọn đúng vòng đời |
| Tạo mới đối tượng/class loader khác | Điểm can thiệp vẫn được áp dụng theo cấu hình thực |

Mỗi dòng nên có ít nhất một test tích cực và một test phủ định liên quan, đặc biệt đối với chính sách bảo mật, audit hoặc cleanup bắt buộc.

## 3. Ví dụ Java 17+: kiểm tra kết quả, số lượt advice và self-invocation

Ví dụ sau dùng **JDK dynamic proxy** cho interface `Counter`. Handler đóng vai trò một advice quan sát; nó tăng các bộ đếm khi đi vào phương thức và khi lời gọi hoàn tất hoặc ném lỗi. Mã đồng thời kiểm tra `add()` gọi `value()` **trực tiếp trên chính target**: lời gọi nội bộ này không đi qua proxy nên không làm tăng bộ đếm của `value()`.

Tạo tệp `AopCompatibilityDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AopCompatibilityDemo {
    interface Counter {
        int add(int delta);
        int value();
    }

    static final class CounterImpl implements Counter {
        private int current;

        @Override
        public int add(int delta) {
            if (delta < 0) {
                throw new IllegalArgumentException("negative delta");
            }
            current += delta;
            return value(); // gọi trên chính target, không qua proxy
        }

        @Override
        public int value() {
            return current;
        }
    }

    static final class Probe {
        int addVisits;
        int valueVisits;
        int returns;
        int failures;
    }

    static Counter instrument(Counter target, Probe probe) {
        return (Counter) Proxy.newProxyInstance(
            Counter.class.getClassLoader(),
            new Class<?>[] { Counter.class },
            (proxy, method, args) -> {
                if (method.getName().equals("add")) {
                    probe.addVisits++;
                } else if (method.getName().equals("value")) {
                    probe.valueVisits++;
                }

                try {
                    Object result = method.invoke(target, args);
                    probe.returns++;
                    return result;
                } catch (InvocationTargetException exception) {
                    probe.failures++;
                    throw exception.getCause();
                }
            }
        );
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        CounterImpl target = new CounterImpl();
        Probe probe = new Probe();
        Counter proxy = instrument(target, probe);

        // Kiểm thử trực tiếp không kích hoạt handler.
        check(target.value() == 0, "initial state");
        check(probe.valueVisits == 0, "direct call bypass");

        // add() gọi value() nội bộ: chỉ add() qua proxy.
        check(proxy.add(7) == 7, "add result");
        check(probe.addVisits == 1, "add intercepted once");
        check(probe.valueVisits == 0, "self call bypass");

        // Gọi value() từ ngoài thông qua proxy.
        check(proxy.value() == 7, "proxied value");

        try {
            proxy.add(-1);
            throw new AssertionError("exception was expected");
        } catch (IllegalArgumentException expected) {
            check(
                expected.getMessage().equals("negative delta"),
                "original exception preserved"
            );
        }

        check(proxy.value() == 7, "state after failure");
        check(probe.addVisits == 2, "add advice count");
        check(probe.valueVisits == 2, "value advice count");
        check(probe.returns == 3, "success path count");
        check(probe.failures == 1, "exception path count");

        System.out.println("Business: OK");
        System.out.println("Advice add: " + probe.addVisits);
        System.out.println("Advice value: " + probe.valueVisits);
        System.out.println("Advice success: " + probe.returns);
        System.out.println("Advice failure: " + probe.failures);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AopCompatibilityDemo.java
java AopCompatibilityDemo
```

Kết quả stdout chính xác khi mọi kiểm tra đạt:

```text
Business: OK
Advice add: 2
Advice value: 2
Advice success: 3
Advice failure: 1
```

**Giải thích số đếm:**

1. `target.value()` chạy trực tiếp nên không kích hoạt handler.
2. `proxy.add(7)` kích hoạt handler ở `add` một lần; lời gọi `value()` bên trong `CounterImpl.add` đi thẳng đến target và không làm tăng `valueVisits`.
3. `proxy.value()` kích hoạt handler ở `value` một lần.
4. `proxy.add(-1)` kích hoạt `add` lần hai rồi target ném `IllegalArgumentException`; handler mở `InvocationTargetException` để bảo toàn nguyên nhân lỗi.
5. `proxy.value()` cuối cùng kích hoạt `value` lần hai; hai lời gọi `value` qua proxy cùng `add(7)` cho ba lần hoàn thành bình thường. Lời gọi `add(-1)` tạo một lượt lỗi.

Các bộ đếm cố ý dùng `int` vì demo chạy tuần tự. Nếu cần kiểm thử concurrent calls, thay bộ đếm bằng cấu trúc đồng bộ thích hợp hoặc lưu sự kiện theo invocation để khẳng định thứ tự mà không tạo data race. Mã minh họa không tự xử lý hợp đồng `equals/hashCode/toString` của dynamic proxy và không đại diện cho mọi cách weaving.

### 3.1. Những kết luận được phép và không được phép rút ra

Được phép kết luận: **với chương trình trên**, khi đi qua JDK dynamic proxy, handler đã được gọi đúng số lần; direct call và self-invocation trên target đã đi vòng qua handler; ngoại lệ đích được chuyển tiếp đúng.

Không được phép kết luận: mọi AOP đều bỏ qua self-invocation; mọi proxy đều dùng reflection; advice đã được instrument đầy đủ ở build production; công cụ code coverage sẽ hiển thị đúng mọi dòng mã biến đổi. Những điều đó cần được kiểm tra riêng trong môi trường AOP thực tế.

## 4. Phân biệt code coverage và độ bao phủ AOP

**Code coverage** thường đánh giá số dòng, nhánh hoặc instruction của mã chương trình đã chạy trong phép thử. **Join-point/advice coverage** lại trả lời các câu hỏi chức năng AOP: bao nhiêu điểm cần chặn được instrument; ở điểm nào điều kiện pointcut đúng; các nhánh của advice nào đã được thử; đường gọi không cần chặn có bị chặn nhầm không.

| Phép đo | Ví dụ câu hỏi | Giới hạn |
|---|---|---|
| Line coverage | Dòng xử lý trong `debit()` đã chạy chưa? | Không khẳng định lời gọi đã đi qua advice |
| Branch coverage | Cả nhánh được phép và bị từ chối đã chạy chưa? | Không đảm bảo đã thử mọi tình huống join point |
| Instruction coverage | Những bytecode instruction nào thực thi? | Mã sinh có thể có vị trí nguồn không rõ |
| Method coverage | Phương thức `transfer()` có từng được chạy? | Không thể hiện số lần interception mong đợi |
| Join-point coverage | Những điểm được chọn bắt buộc có chặn thật không? | Cần tập mong đợi do thiết kế/kiểm thử định nghĩa |
| Pointcut negative coverage | Những phương thức không thuộc phạm vi có bị advice chạy nhầm không? | Cần ca phủ định, không suy ra từ line coverage |
| Advice-path coverage | Before, normal return, exception, short-circuit, retry đã được thử? | Cần instrument hoặc assertion riêng về advice |
| Outcome / contract coverage | Caller nhìn thấy đúng kết quả, ngoại lệ và side effect? | Không được thay bằng bộ đếm mà không xét chức năng |

Một điểm quan trọng: **100% line coverage không phải bằng chứng pointcut đúng**. Các dòng trong target có thể được gọi trực tiếp khi hệ thống production lẽ ra phải đi qua proxy; các advice có thể chỉ chạy ở test khác hoặc bị loại khỏi báo cáo coverage. Ngược lại, chỉ số advice hit cao cũng không chứng minh đủ trường hợp lỗi và phủ định.

### 4.1. Thiết lập ma trận bao phủ join point

Ví dụ bảng kiểm thử tự quản lý:

| Điểm thực thi / đường gọi | Chính sách mong đợi | Test tích cực | Test phủ định | Bằng chứng |
|---|---|---|---|---|
| `payment.authorize()` từ biên công khai | Phải kiểm tra quyền | Có | Không đủ quyền | Assert quyết định và audit |
| `payment.capture()` thành công | Phải ghi audit | Có | Input không hợp lệ | Assert số bản ghi và nội dung |
| `payment.capture()` ném lỗi | Phải ghi lỗi/cleanup khi quy định | Có | Không có lỗi | Assert đường exception/finally |
| `payment.balance()` | Không chạy audit thay đổi | Có | Gọi lặp lại | Assert không có audit |
| `payment.capture()` gọi nội bộ | Tùy cơ chế AOP, nhưng chính sách phải rõ | Có | Gọi bên ngoài | Assert đường interception thực tế |

Đây là bảng phương pháp; tên phương thức minh họa. “Độ bao phủ join point 100%” chỉ có ý nghĩa nếu **tập điểm bắt buộc được định nghĩa đầy đủ**, bao gồm những đường gọi làm phát sinh tác dụng phụ. Cần kiểm tra cả điểm bị chặn nhầm để tránh một pointcut quá rộng.

### 4.2. Không đánh đồng lời gọi và lần thực thi

Một join point **method call** được xác định tại nơi gọi; một join point **method execution** được xác định tại nơi phương thức chạy. Trong hệ thống có nhiều caller, một execution có thể được đi vào từ nhiều call site; trong retry/recursive calls, số lần gọi và số lần thực thi có thể khác nhau. Khi báo cáo coverage, cần ghi rõ đơn vị đếm: call site, execution, event nghiệp vụ, lần vào interceptor hay số lần target chạy.

Nếu advice around có thể không gọi hoặc gọi `proceed()` nhiều lần, số “advice hit” càng không đồng nhất với “số lượt nghiệp vụ hoàn thành”.

## 5. Vì sao weaving và công cụ coverage có thể tương tác?

Các công cụ coverage Java thường chèn logic đếm hoặc dùng runtime agent để quan sát bytecode. Một cơ chế AOP có thể chèn advice vào cùng class. **Hai phép biến đổi có thể tác động lên cùng bytecode**, vì vậy thứ tự, thời điểm và phạm vi instrument ảnh hưởng khả năng báo cáo hoặc gỡ lỗi.

### 5.1. Các giai đoạn có thể xuất hiện

```text
Mã nguồn .java
    │
    ▼
Biên dịch (javac)
    │
    ▼
Class bytecode ban đầu
    │
    ├── [A] Weave advice khi biên dịch / hậu biên dịch
    │        └── Coverage instrument khi chạy
    │
    ├── [B] Coverage instrument offline
    │        └── Weave trên bytecode đã instrument
    │
    └── [C] Nạp class qua một hoặc nhiều agent/transformer
             └── thứ tự biến đổi phụ thuộc cấu hình runtime
    │
    ▼
Bytecode cuối cùng JVM thực thi
    │
    ▼
Dữ liệu coverage + stack trace + kết quả kiểm thử
```

Đây là các **khả năng triển khai**; không có thứ tự chung đúng cho tất cả công cụ. Một số công cụ không hỗ trợ mọi kết hợp hoặc có quy tắc riêng về instrument offline, class loader, retransform và định danh bytecode. Cần dựa vào tài liệu của công cụ đang dùng và kiểm tra pipeline thật.

### 5.2. Các dấu hiệu xung đột đáng điều tra

- Coverage trên test class bị trống hoặc thấp bất thường dù breakpoint thấy code đã chạy.
- Cùng một file nguồn có report khác nhau giữa test thường và test có weaving.
- Class đã instrument trước đó bị báo lỗi khi instrument lần nữa, hoặc xuất hiện lỗi verify/link.
- Các phương thức tổng hợp (*synthetic*), bridge, accessor hoặc code sinh ra xuất hiện trong report làm lệch tỷ lệ mong đợi.
- Không khớp checksum/class id hoặc thông tin debug của class được báo cáo với bytecode thật trong runtime.
- Class đã thay đổi nhưng report dùng bản cũ; cache, incremental build hoặc thứ tự agent là một khả năng cần kiểm chứng.
- Breakpoint đặt trên source không dừng ở vị trí kỳ vọng, nhưng stack trace cho thấy code đã biến đổi vẫn chạy.

Các triệu chứng này **không tự động chứng minh lỗi do AOP**. Có thể là build profile, classpath, agent chưa được bật, khác JDK, test bị bỏ qua hoặc report filter.

### 5.3. Cách chẩn đoán có kiểm soát

Thực hiện bốn cấu hình trên cùng bài test và cùng class mục tiêu nếu bộ công cụ hỗ trợ:

| Cấu hình | AOP | Coverage | Mục tiêu |
|---|---|---|---|
| Baseline | Tắt | Tắt | Hợp đồng nghiệp vụ gốc |
| AOP only | Bật | Tắt | Advice và pointcut hoạt động đúng |
| Coverage only | Tắt | Bật | Report coverage bình thường |
| Combined | Bật | Bật | Kiểm chứng tương thích và độ trung thực của report |

Ghi lại **JDK, tham số JVM, phiên bản công cụ, tập class được biến đổi, class loader, cách instrument và bản build**. Nếu chỉ cấu hình combined bị lỗi, tiếp tục kiểm tra thứ tự biến đổi/agent theo tài liệu. Nếu AOP only đã sai, sửa phạm vi pointcut hoặc trình tự advice trước; không sửa report coverage để che lỗi.

### 5.4. Source mapping và lọc báo cáo

Bytecode weave hoặc sinh proxy có thể mang line-number table, frame và phương thức tổng hợp khác với mã nguồn gốc. Coverage report có thể lọc một số phần sinh ra hoặc tính các nhánh không có dòng nguồn trực tiếp. Do đó:

- Đối chiếu số liệu coverage với **bản class thực sự được nạp**.
- Phân biệt code tự viết, advice tự viết, mã sinh do compiler và mã do công cụ instrument.
- Nếu cần loại trừ mã sinh khỏi KPI, ghi rõ tiêu chí exclude và kiểm tra liệu exclude có vô tình che advice quan trọng không.
- Không tự tăng tỷ lệ coverage bằng cách bỏ cả những module AOP cần test.
- Khi classpath có nhiều bản class trùng tên, phải xác minh bản nào được loader chọn.

Một số công cụ như JaCoCo hỗ trợ line/branch coverage cho bytecode Java, nhưng chi tiết tương thích với biến đổi mã phải xác nhận theo phiên bản và cấu hình đang sử dụng; tên công cụ không bảo đảm tự giải quyết mọi trường hợp weaving.

## 6. Kiểm tra tính tương thích khi đóng gói và triển khai

Môi trường kiểm thử có thể khác production ở những điểm quan trọng:

1. **Compile-time vs load-time weaving:** Nếu test chạy class chưa weave nhưng production chạy class đã weave, kết quả unit test không chứng minh advice production. Điều ngược lại cũng đúng.
2. **Proxy được dựng ở đâu:** Test trực tiếp tạo target không đại diện cho object thực tế được bọc trong cấu hình ứng dụng.
3. **Agent và JVM flags:** Runtime thiếu agent hoặc cấu hình mở truy cập/module có thể khiến việc can thiệp không thực hiện hoặc báo lỗi.
4. **Class loader:** Môi trường plugin/module, test runner và runtime có thể nạp lớp qua loader khác nhau; matcher, cache metadata và cơ chế weaving cần được kiểm tra.
5. **Classpath và thứ tự phụ thuộc:** Version mismatch, nhiều class cùng tên hoặc công cụ biến đổi lặp làm kết quả khác bản test.
6. **Chế độ tối ưu build:** Mã sinh/obfuscation/shading có thể đổi tên, metadata hoặc debug symbols mà pointcut hay debugger dựa vào.
7. **Khởi tạo và lifecycle:** Advice có thể đọc dữ liệu chưa sẵn sàng ở startup, static init hoặc constructor; không được giả định các join point đó luôn được hỗ trợ.
8. **Bất đồng bộ:** Invocation context có thể không đi theo thread hoặc callback nếu chưa có propagation; test đồng bộ không bắt được lỗi này.

Nên có ít nhất một **smoke test dùng đúng artifact chạy thực tế** (class/jar và tham số runtime phù hợp) để kiểm chứng một join point đại diện: advice khớp, target chạy đúng, đường lỗi đúng và log/metric cần thiết xuất hiện. Test đó không thay thế kiểm thử đầy đủ nhưng giúp phát hiện khác biệt giữa pipeline test và triển khai.

### 6.1. Kiểm tra điều kiện tiên quyết của weaving

Với triển khai có weaving, tài liệu cấu hình cần trả lời được:

- Weave ở bước biên dịch, sau biên dịch hay lúc class loading?
- Class/jar nào được biến đổi, class nào bị exclude?
- Những thư viện nào chứa runtime của advice và chúng có mặt trong artifact cuối không?
- Dữ liệu debug (line numbers, local variables, source file) có được giữ?
- Agent coverage và agent weaving được nạp theo thứ tự nào, và tổ hợp đó có được hỗ trợ?
- Có dự phòng nếu không instrument được một class bắt buộc hay không?
- Báo cáo build có bằng chứng rằng các class cần weave đã được xử lý chưa?

Không được coi một log kiểu “weaving initialized” là bằng chứng mọi join point mong muốn đã được can thiệp. Test hành vi tại join point vẫn là nguồn bằng chứng quyết định.

## 7. Gỡ lỗi khi luồng điều khiển đi qua advice

### 7.1. Stack trace có thể xuất hiện các khung trung gian

Ví dụ minh họa, **không phải stack trace cố định của Java**:

```text
Caller
  → generated proxy / dispatch handler
    → interceptor A (before)
      → interceptor B (around)
        → target method
      ← interceptor B (after / exception)
    ← interceptor A (after)
  ← Caller
```

Trong exception path, khi một advice bắt và chuyển đổi exception, stack trace có thể chỉ rõ vị trí ném mới thay vì vị trí tạo lỗi đầu tiên. Các wrapper reflection như `InvocationTargetException` hoặc proxy wrapper theo quy tắc Java cũng có thể xuất hiện nếu không được xử lý theo hợp đồng.

Cách đọc stack trace có hệ thống:

1. Xác định exception gốc, `cause` và các exception bị suppressed.
2. Tìm frame ứng dụng đầu tiên liên quan lỗi thực; phân biệt frame của advice, proxy và target.
3. Xác định lời gọi target đã xảy ra chưa, xảy ra mấy lần, và có advice nào short-circuit không.
4. Đối chiếu line number với artifact bytecode đang chạy.
5. Kiểm tra exception có bị advice nuốt, bọc thêm, đổi kiểu hoặc ghi đè trong `finally` không.

**Không kết luận “lỗi nằm ở proxy” chỉ vì frame proxy nằm gần đầu stack trace.** Proxy có thể chỉ là nơi lỗi đi qua.

### 7.2. Đặt breakpoint đúng vị trí

Một chuỗi breakpoint có ích cho đường gọi qua proxy là:

```text
(1) Caller trước khi gọi
(2) Proxy/handler hoặc interception entry point
(3) Điều kiện pointcut động (nếu có)
(4) Advice trước proceed
(5) Target method
(6) Advice sau proceed / catch / finally
(7) Caller nhận kết quả hoặc lỗi
```

Nếu breakpoint ở advice không dừng, cần phân biệt:

- Test đang gọi trực tiếp target?
- Join point có thuộc phạm vi pointcut?
- Advice có được instrument và nạp chưa?
- Breakpoint có ánh xạ đúng bytecode đang chạy?
- Đường execution đã đi qua advice khác short-circuit chưa?

Nếu breakpoint ở target dừng nhưng không có frame của advice, có thể lời gọi đi vòng proxy hoặc class thực tế không được weave. Nếu advice dừng mà target không dừng, có thể advice around chặn lời gọi theo thiết kế hoặc đã ném lỗi trước `proceed()`.

### 7.3. Thông tin debug khi biến đổi bytecode

Khi có weaving, các bảng như `LineNumberTable` và `LocalVariableTable` ảnh hưởng khả năng trình gỡ lỗi ánh xạ bytecode về nguồn. Dùng công cụ JDK thích hợp để xem class đã build:

```bash
javap -c -l -p com.example.Demo
```

Lệnh này chỉ là **ví dụ cú pháp**: class `com.example.Demo` phải tồn tại trên classpath, và khi cần phải thêm `-classpath <đường-dẫn-class-hoặc-jar>`. `javap` cho thấy bytecode, line numbers nếu được biên dịch kèm debug information, và cấu trúc phương thức; nó không tự chứng minh JVM đang dùng đúng file class vừa xem. Muốn xác minh class runtime, cần đối chiếu class loader, code source và bản artifact đã nạp.

Việc bật/giữ metadata debug có thể cải thiện khả năng theo dõi nhưng phải nhất quán với cách build; obfuscation hoặc stripping metadata có thể khiến dòng nguồn thiếu hoặc lệch. Không chỉnh mã production theo stack frame do mã sinh nếu chưa xác nhận source mapping.

### 7.4. Log và trace phải gắn với invocation cụ thể

Khi instrument nhiều advice, log “before” và “after” thiếu định danh có thể xen kẽ giữa các thread, làm người đọc hiểu sai thứ tự. Nên thêm correlation ID/trace ID phù hợp, tên join point và trạng thái outcome; khi cần, ghi một sự kiện rõ ràng cho đường exception.

Tuy nhiên, công cụ chẩn đoán tự làm thay đổi tải hệ thống. Không stringify toàn bộ đối số, stack trace hoặc ghi I/O đồng bộ ở mọi hot path chỉ để tìm một lỗi hiếm. Dùng log có điều kiện, sampling chẩn đoán khi chính sách cho phép, giới hạn dữ liệu nhạy cảm và quan sát tác động performance.

## 8. Gỡ lỗi các tình huống AOP khó

### 8.1. Self-invocation và gọi vòng qua proxy

Lời gọi từ một method đến method khác trên cùng target thường không đi qua **proxy bên ngoài**; ví dụ Java ở trên chứng minh trường hợp này. Với weaving, một số self-invocation có thể vẫn là join point hợp lệ. Vì vậy cần kiểm tra:

- Caller giữ tham chiếu đến proxy hay target?
- Join point là method call hay method execution?
- Method có thể được cơ chế instrument chặn không?
- Việc bỏ qua advice là một phần hợp đồng hay là lỗi bảo mật/quan sát?

Nếu advice kiểm tra quyền bắt buộc phải bao phủ đường gọi nội bộ, cần chọn ranh giới kiểm soát và cơ chế phù hợp, không chỉ dựa vào test gọi từ ngoài.

### 8.2. Multiple advice và thứ tự quanh `proceed()`

Với hai advice around, kết quả thường có cấu trúc lồng nhau:

```text
A before
  B before
    target
  B after
A after
```

Nếu B không gọi `proceed()`, target không chạy; nếu B retry, target có thể chạy nhiều lần. Kiểm thử cần assert **thứ tự, số lần và outcome**, chứ không chỉ đếm code line. Với `try/finally`, cleanup chạy khi có lỗi; còn “after returning” chỉ dành cho hoàn thành bình thường. Đừng thay tương đương hai loại này khi sửa lỗi.

### 8.3. Exception wrapping

Reflection `Method.invoke` đóng gói lỗi ném bởi target trong `InvocationTargetException`. Một handler có thể mở `getCause()` để duy trì loại lỗi gốc, nhưng giao diện proxy còn có quy tắc riêng đối với checked exception chưa khai báo. Trong kiểm thử:

- Assert loại exception mà **caller thực sự nhận**.
- Assert `cause`/suppressed khi hợp đồng yêu cầu.
- Đảm bảo advice exception handling không biến lỗi thành thành công giả.
- Thử trường hợp lỗi do advice và lỗi do target, vì cách xử lý có thể khác nhau.

### 8.4. Concurrency và context propagation

Nếu advice dùng `ThreadLocal`, test một luồng có thể luôn qua. Trong môi trường thread pool:

- Giá trị cũ có thể rò sang tác vụ mới nếu không dọn.
- Context không tự xuất hiện ở thread khác trong mọi mô hình async.
- Một invocation state dùng chung có thể khiến chỉ số interceptor hoặc đối số bị ghi đè.
- Thứ tự log không tương đương thứ tự nghiệp vụ khi nhiều thread.

Kiểm thử đồng thời cần xác nhận cách ly định danh, cleanup sau exception, propagation khi chuyển thread và tính đúng đắn của counter. Không dùng số đếm `int` không đồng bộ trong một demo nhiều luồng rồi diễn giải sai kết quả như lỗi của AOP.

### 8.5. Điểm chặn trùng lặp

Một ứng dụng có thể bị áp advice hai lần do cả proxy lẫn weaving, nhiều lớp decorator, cấu hình lặp hoặc hai chain khác nhau. Triệu chứng gồm audit trùng, metric bị nhân đôi, `proceed()` lồng bất ngờ và stack trace dài. Cần đối chiếu identity của object, đường dispatch và danh sách cơ chế can thiệp thực tế. Kiểm thử “mỗi sự kiện nghiệp vụ tạo đúng số side effect” giúp phát hiện tốt hơn một test chỉ nhìn kết quả trả về.

## 9. Quy trình kiểm chứng tương thích cho dự án

### 9.1. Trước khi thay đổi cấu hình AOP

1. Ghi rõ hợp đồng chức năng của từng advice: trường hợp phải chạy, được bỏ qua, thứ tự, kết quả, side effects và lỗi.
2. Lập danh sách pointcut dự kiến gồm join point bắt buộc và những điểm không được can thiệp.
3. Xác nhận cách triển khai: proxy, generated subclass, weaving hoặc kết hợp; xác nhận điểm giới hạn của cơ chế.
4. Ghi lại JDK, pipeline biên dịch, classpath, agent, bộ đo coverage và cách chạy test.
5. Có baseline gồm test nghiệp vụ, test advice, test tích hợp, code coverage và một phép đo hành vi/hiệu năng đại diện.

### 9.2. Sau khi thay đổi

1. Chạy test nghiệp vụ thuần để phát hiện hồi quy ngoài AOP.
2. Chạy test hợp đồng advice với cả thành công và ngoại lệ.
3. Chạy test tích hợp trên **đúng đường được instrument**, kiểm tra cả join point chọn và không chọn.
4. So coverage line/branch/instruction với baseline; điều tra thay đổi bất thường do bytecode biến đổi.
5. Xem advice-hit/pointcut matrix, bởi chỉ số line coverage không đo được điều kiện chặn.
6. Chạy tổ hợp AOP + coverage và xác nhận không có xung đột agent/bytecode.
7. Chạy smoke test artifact triển khai thật với agent/weaving runtime tương ứng.
8. Khi thất bại, dùng breakpoint ở cả interception entry và target, đối chiếu class loader/bytecode rồi sửa đúng nguyên nhân.
9. Lặp lại các kiểm thử liên quan sau khi sửa và xác nhận báo cáo không bỏ sót bằng cách exclude sai phạm vi.

### 9.3. Những bằng chứng nên lưu cho một thay đổi AOP

| Bằng chứng | Ý nghĩa khi review |
|---|---|
| Ma trận join point / pointcut | Chứng minh phạm vi mong đợi đã được xác định |
| Test assertions cho advice | Chứng minh hành vi chạy đúng, gồm exception/finally |
| Negative tests | Chứng minh điểm không thuộc phạm vi không bị chặn nhầm |
| Báo cáo line + branch coverage | Cho biết phần mã test thực thi theo tiêu chí đo |
| Advice hit / execution counts | Chỉ rõ mức bao phủ interception trên tập join point |
| Danh sách class đã instrument | Chứng minh pipeline đã xử lý các class cần thiết |
| Runtime/JVM args và phiên bản tool | Giúp tái hiện điều kiện thực thi |
| Smoke test từ artifact cuối | Giảm rủi ro môi trường test khác deployment |
| Stack trace hoặc log có correlation | Giúp truy tìm lỗi ở đúng invocation |

Có thể bổ sung mutation testing để kiểm chứng test thực sự phát hiện sai lệch, chẳng hạn cố tình đảo điều kiện pointcut, bỏ một lần gọi `proceed()` hoặc thay đường xử lý exception trong môi trường test cô lập. Đo được nhiều dòng không đảm bảo assert tốt; một mutation sống sót có thể cho thấy thiếu kiểm tra về advice hoặc outcome. Mutation chỉ có giá trị khi biến thể cố tình sai làm thay đổi ngữ nghĩa cần bảo vệ và test có cơ hội quan sát.

## 10. Những sai lầm phổ biến

1. **“Phương thức đích đã được unit test thì advice đã được test.”** Sai; unit test có thể gọi thẳng target, bỏ qua proxy hoặc weaving thực tế.
2. **“Line coverage 100% nghĩa là mọi join point được chặn.”** Sai; code coverage và join-point coverage có mẫu số khác nhau.
3. **“Mock target luôn tương đương test proxy.”** Sai; phải biết mock đứng trước hay sau ranh giới interception.
4. **“Bật agent coverage không ảnh hưởng gì đến weaving.”** Không thể mặc định; các công cụ có thể cùng biến đổi bytecode, cần xác nhận compatibility.
5. **“Break point không dừng là pointcut sai.”** Có thể do khác class, debug symbols, class loader, advice short-circuit hoặc đường gọi vòng qua proxy.
6. **“Mọi lời gọi nội bộ đều không bị chặn.”** Đây là đặc tính của một số proxy, không phải quy luật áp dụng cho mọi kiểu AOP.
7. **“Test chỉ đường thành công là đủ.”** Sai; after throwing, finally, retry, cleanup và exception wrapping có thể bị lỗi riêng.
8. **“Số advice hit bằng số lần target chạy.”** Không đảm bảo khi có short-circuit, retry, nested advice hoặc nhiều tầng interception.
9. **“Report coverage khác nhau thì test code đã sai.”** Cần loại trừ thay đổi bytecode, agent, build artifact và report filters trước.
10. **“Đổi thứ tự advice chỉ ảnh hưởng log.”** Sai; có thể làm thay đổi kiểm tra quyền, kết quả, ngoại lệ và dọn tài nguyên.
11. **“Gỡ lỗi có thể luôn xem stack trace như Java không instrument.”** Lớp dispatch, proxy generated, reflection và mã weave có thể thêm hoặc thay frame.
12. **“Unit test pass trên một JDK bảo đảm runtime mọi môi trường giống nhau.”** Class loader, module access, version, agent và trình tự biến đổi có thể khác.
13. **“Loại bỏ mã AOP khỏi coverage để báo cáo đẹp hơn.”** Nếu vô tình exclude logic advice có yêu cầu chức năng, metric không còn phản ánh rủi ro.
14. **“Thêm logging dày đặc vào mọi advice là cách debug miễn phí.”** Nó có thể đổi timing, che race, tăng I/O và giữ dữ liệu nhạy cảm.

## 11. Bài tập thực hành

### Bài tập 1: Chứng minh phạm vi pointcut

Xây hai phương thức `read()` và `write()` trên cùng một interface. Dùng proxy chỉ ghi nhận `write()`. Viết ba test: gọi `read()` không có advice; gọi `write()` có đúng một advice; gọi `write()` với input lỗi kiểm chứng exception và số lần advice. Sau đó thử pointcut rộng chọn cả hai method để xem negative test có bắt lỗi không.

### Bài tập 2: So sánh report coverage với advice-hit matrix

Với một phương thức được unit test trực tiếp và integration test qua proxy, ghi hai kết quả: phương thức đã được code coverage đánh dấu là chạy hay chưa; advice-hit counter có tăng hay chưa. Giải thích vì sao một phép đo có thể dương trong khi phép đo kia bằng 0.

### Bài tập 3: Điều tra tương tác instrument

Trong một dự án thử nghiệm hỗ trợ weaving và coverage agent, chạy bốn cấu hình baseline, AOP only, coverage only và combined. Lưu classpath, JVM args, version và report. Nếu có chênh lệch, kiểm tra tài liệu về thứ tự biến đổi, thử cấu hình được hỗ trợ và đối chiếu class thật trước khi kết luận.

### Bài tập 4: Tái hiện lỗi do đường gọi nội bộ

Chạy `AopCompatibilityDemo` và xác nhận `valueVisits` vẫn bằng 0 ngay sau `proxy.add(7)`. Sau đó sửa target để một caller bên ngoài gọi `proxy.value()`, quan sát lượt mới. Từ đó giải thích: chính sách AOP của ứng dụng cần bắt **method execution** hay chỉ các lời gọi đi qua proxy?

## 12. Câu hỏi tự kiểm tra

**1. Điều gì khác giữa test logic advice và test tích hợp AOP?** Test logic advice kiểm chứng thân xử lý trong một harness hoặc context giả lập; test tích hợp chứng minh hệ thống thật chọn join point và kích hoạt advice theo đường instrument cần dùng.

**2. Tại sao line coverage có thể 100% khi audit bị bỏ sót?** Vì target vẫn chạy đầy đủ từ đường không qua AOP; bộ đếm dòng không tự xác minh mọi yêu cầu audit tại join point.

**3. Khi nào hai agent Java có thể gây vấn đề?** Khi chúng cùng biến đổi bytecode theo thứ tự hoặc chế độ mà công cụ không hỗ trợ; cần kiểm tra tài liệu, cấu hình, class thực và tổ hợp riêng rẽ.

**4. Vì sao test chỉ assert số lần advice chạy chưa đủ?** Advice vẫn có thể ghi sai dữ liệu, sai thứ tự, nuốt exception hoặc thay đổi kết quả. Cần assert cả hành vi quan sát được.

**5. Self-invocation có luôn bỏ qua advice không?** Không. Nó có thể đi vòng proxy trong một số triển khai; weaving có thể can thiệp ở điểm thực thi tùy khả năng cơ chế.

**6. Muốn debug advice không chạy thì kiểm tra gì đầu tiên?** Xác nhận đang gọi object thật sự được instrument, pointcut đúng, class được nạp đúng phiên bản và không có advice khác chặn đường tiếp tục.

**7. Tại sao cần test artifact cuối?** Vì class đã weave, agent/JVM flags, class loader và runtime dependencies ở bản triển khai có thể khác môi trường unit test.

**8. Có nên exclude toàn bộ code sinh hoặc advice khỏi báo cáo coverage?** Chỉ nên áp dụng filter có lý do và đủ hẹp; vẫn phải giữ phép kiểm chứng bắt buộc của advice và tập join point ở các test riêng.

**9. Làm sao phân biệt target ném lỗi với handler tạo lỗi?** Kiểm tra exception type, cause chain, stack frames và breakpoint ở điểm gọi `proceed()` hoặc `Method.invoke`; mở wrapper đúng cách khi hợp đồng yêu cầu.

**10. Đo bao phủ AOP thế nào để tránh “chỉ số đẹp” giả?** Bắt đầu từ tập join point cần chặn và tập không được chặn do yêu cầu xác định; thử thành công/lỗi, internal/external calls, kiểm chứng hit, outcome và sự kiện thực tế thay vì chỉ cộng số dòng hoặc tỷ lệ.

**Ghi nhớ:** Việc tương thích AOP với kiểm thử, coverage và debugger là một vấn đề **hành vi và bằng chứng thực thi**. Phải kiểm tra đường can thiệp thực, test cả điểm khớp và không khớp, tách code coverage khỏi join-point/advice coverage, xác minh cách bytecode được instrument và sử dụng kết quả debug đúng với artifact runtime.