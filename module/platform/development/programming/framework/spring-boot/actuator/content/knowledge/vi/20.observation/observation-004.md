# Quản lý vòng đời start, scope, error và stop

## 1. Hai việc cần quản lý: công việc được đo và phạm vi đang hiện hành

Khi quan sát một thao tác như xử lý đơn hàng, ta cần xác định thời điểm bắt đầu/kết thúc và ghi nhận lỗi nếu có. Đồng thời, mã chạy bên trong thao tác cần biết nó đang thuộc observation nào, để các lời gọi lồng nhau có thể gắn với đúng ngữ cảnh.

Micrometer tách hai nhu cầu này:

- **Vòng đời observation:** xác định công việc bắt đầu và kết thúc.
- **Vòng đời scope:** xác định observation nào đang hiện hành trong một đoạn thực thi.

Có thể hình dung observation như một lần bấm đồng hồ đo cho công việc, còn scope như việc đưa tên công việc ấy vào vị trí “đang xử lý” của luồng. Bấm dừng đồng hồ và xóa vị trí hiện hành là hai hành động khác nhau.

```text
Observation:   tạo → start ------------------------------→ stop
Scope:                     open → thực thi → close
Lỗi nếu có:                           error(ex)
```

Sơ đồ thể hiện các vai trò, không áp đặt rằng `error(ex)` luôn nằm trước `close`. Vị trí báo lỗi phụ thuộc cách viết try/catch và API bao công việc.

Sai một trong hai vòng đời có thể tạo hai loại vấn đề:

1. Quên `stop()`: bộ xử lý quan sát không nhận được tín hiệu hoàn tất đúng lúc.
2. Quên đóng scope: observation cũ có thể còn hiện hành khi luồng tiếp tục xử lý một việc khác.

Bài này dùng thực thi đồng bộ để giải thích đầy đủ hai vòng đời, sau đó chỉ ra điều cần thay đổi khi công việc chạy bất đồng bộ. Mô hình các tín hiệu được mô tả trong [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

## 2. Bốn thao tác không thay thế lẫn nhau

| Thao tác | Trách nhiệm | Không được tự suy ra |
| --- | --- | --- |
| `start()` | Bắt đầu observation và thông báo mốc bắt đầu cho handler phù hợp | Không tự làm observation thành hiện hành trong luồng |
| `openScope()` | Đưa observation vào phạm vi hiện hành và trả về tài nguyên scope cần đóng | Không thay cho `start()` hoặc `stop()` |
| `error(ex)` | Ghi/báo lỗi cho observation | Không tự ném lại ngoại lệ, rollback hoặc dừng observation |
| `stop()` | Kết thúc observation và thông báo mốc hoàn tất | Không thay việc đóng scope |

Khi handler hỗ trợ context đang dùng, các tín hiệu này tương ứng với `onStart`, `onScopeOpened`, `onError` và `onStop`. Việc đóng scope có callback `onScopeClosed`. Đầu ra thực tế còn phụ thuộc handler: cùng một vòng đời có thể phục vụ đo thời gian, tracing hoặc một hành vi quan sát riêng.

### 2.1. Tạo chưa bắt đầu để chuẩn bị metadata

```java
Observation observation = Observation.createNotStarted(
        "orders.process", registry)
        .lowCardinalityKeyValue("channel", "web");
```

Đây là đoạn trích, giả định đã có `ObservationRegistry registry`. Sau lời gọi trên, observation chưa được bắt đầu. Ta có thể chuẩn bị tên/nhãn và dữ liệu đầu vào cần thiết trước khi handler nhận mốc bắt đầu.

Nếu kết thúc phương thức ngay sau đoạn trích mà không gọi `start()` hoặc một API quản lý vòng đời như `observe(...)`, chưa có một khoảng công việc được quan sát hoàn chỉnh.

Cũng có cách tạo và bắt đầu ngay:

```java
Observation observation = Observation.start("orders.process", registry);
```

Cách này hữu ích khi muốn bắt đầu tại đúng vị trí đó. Đừng gọi thêm `start()` vì quên rằng helper đã bắt đầu observation.

### 2.2. Bắt đầu không có nghĩa đã mở scope

Với registry được cấu hình để quan sát và chưa có observation bên ngoài, sau `start()`, `registry.getCurrentObservation()` vẫn có thể là `null`.

Điều này không chứng minh observation chưa bắt đầu. Nó chỉ cho biết chưa có observation hiện hành trong phạm vi đang xét.

Để mã bên trong thấy observation đó là hiện hành:

```java
try (Observation.Scope scope = observation.openScope()) {
    // Các lời gọi đồng bộ trong phạm vi này có thể tìm current observation.
}
```

Đây chỉ là đoạn quản lý scope. Observation bao ngoài vẫn cần được bắt đầu và dừng bởi nơi sở hữu vòng đời.

### 2.3. Báo lỗi và truyền lỗi cho bên gọi là hai trách nhiệm

```java
observation.error(ex);
throw ex;
```

Dòng đầu phục vụ quan sát. Dòng sau duy trì luồng ngoại lệ cho bên gọi.

Nếu chỉ báo lỗi rồi trả về kết quả thành công giả, mã gọi có thể hiểu sai kết quả nghiệp vụ. Nếu chỉ ném lỗi trong một cấu trúc quản lý thủ công mà không báo cho observation, handler có thể không nhận tín hiệu lỗi tương ứng.

Một thao tác nghiệp vụ trả về giá trị “bị từ chối” mà không ném exception cũng không tự làm `onError` xuất hiện. Phải xác định quy ước: đó là một kết quả bình thường để phân nhóm, hay một thất bại cần ghi nhận bằng cơ chế lỗi. Không biến mọi nhánh điều kiện thành exception chỉ để tạo thêm telemetry.

### 2.4. Dừng không đồng nghĩa đã xuất dữ liệu đến backend

`stop()` là tín hiệu kết thúc tại cơ chế quan sát. Handler có thể hoàn tất timer hoặc span ở mốc này, nhưng việc gửi/lưu dữ liệu ở hệ thống bên ngoài còn phụ thuộc registry, exporter và đường truyền.

Do đó, “đã gọi stop” và “đã nhìn thấy số liệu trên dashboard” là hai mốc khác nhau. Không thêm một vòng `stop()` khác chỉ vì dashboard chưa cập nhật.

## 3. Mẫu quản lý thủ công cho công việc đồng bộ

Giả sử `processOrder()` là phương thức nghiệp vụ của ứng dụng. Đoạn trích sau thể hiện việc sở hữu vòng đời tường minh:

```java
Observation observation = Observation.createNotStarted(
        "orders.process", registry)
        .lowCardinalityKeyValue("channel", "web");

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    processOrder();
}
catch (RuntimeException | Error ex) {
    observation.error(ex);
    throw ex;
}
finally {
    observation.stop();
}
```

`processOrder()` không phải API của Micrometer; đoạn trích minh họa chỗ đặt nghiệp vụ, không phải một chương trình độc lập. Chương trình chạy được sẽ có đầy đủ ở phần thực hành.

### 3.1. Vì sao scope nằm trong try-with-resources?

`Observation.Scope` là tài nguyên cần được đóng. Try-with-resources đóng nó khi khối lệnh kết thúc bình thường, ném ngoại lệ hoặc rời khối bằng `return`.

Điều cần được khôi phục là **phạm vi trước đó**. Trong một tác vụ không có observation bao ngoài, current có thể trở về `null`. Trong một tác vụ có observation cha đang hiện hành, current phải trở về observation cha, không phải luôn luôn thành `null`.

Đừng thay việc đóng scope bằng cách tự gán current về rỗng. Làm vậy có thể phá observation đang bao quanh công việc con.

### 3.2. Vì sao stop nằm trong finally?

Nghiệp vụ có nhiều đường thoát: chạy hết, trả về sớm hoặc ném lỗi. Đặt `stop()` chỉ sau dòng nghiệp vụ sẽ bỏ sót các đường không đi đến dòng đó.

```java
observation.start();
processOrder();
observation.stop();
```

Đoạn trên là ví dụ **thiếu quản lý đường lỗi**: nếu `processOrder()` ném ngoại lệ, dòng `stop()` không được thực hiện. Nó cũng chưa mở scope nếu các lời gọi bên trong cần current observation.

Trong mẫu đúng, `finally` chịu trách nhiệm kết thúc observation do chính phương thức này tạo/bắt đầu. Không dùng `finally` để dừng cả observation của framework hoặc của bên gọi.

### 3.3. Vì sao catch nằm sau khối tài nguyên?

Trong mẫu trên, nếu nghiệp vụ ném lỗi:

```text
nghiệp vụ ném lỗi
    → try-with-resources đóng scope
    → catch gọi error(ex)
    → catch ném lại lỗi
    → finally gọi stop()
    → lỗi tiếp tục đi đến bên gọi
```

Bởi vậy, `onError` ở đường này có thể được gọi sau khi observation không còn là current. Callback phải đọc context được truyền vào, không đoán observation từ current của registry.

Nếu cần báo lỗi khi scope còn mở, có thể đặt một try/catch nghiệp vụ bên trong scope. Khi thay vị trí catch, thứ tự `error` và `close` thay đổi. Không cần đổi cấu trúc chỉ để ép một thứ tự callback nếu không có yêu cầu cụ thể; ưu tiên một nơi sở hữu vòng đời rõ ràng.

### 3.4. Checked exception cần được xử lý theo hợp đồng thực tế

Mẫu catch `RuntimeException | Error` không bao phủ một checked exception được phương thức nghiệp vụ khai báo.

Ví dụ một hàm tiện ích đồng bộ nhận `Callable<T>` có thể quản lý cả kết quả trả về lẫn checked exception như sau. Đây là một phương thức đặt trong lớp tiện ích, cần các import `java.util.concurrent.Callable`, `Observation` và `ObservationRegistry`:

```java
static <T> T observeCall(ObservationRegistry registry,
                         Callable<T> action) throws Exception {
    Observation observation =
            Observation.start("orders.process", registry);
    try (Observation.Scope scope = observation.openScope()) {
        return action.call();
    }
    catch (Exception | Error ex) {
        observation.error(ex);
        throw ex;
    }
    finally {
        observation.stop();
    }
}
```

`return action.call()` không bỏ qua cleanup: Java vẫn đóng tài nguyên và thực hiện `finally` trước khi trả kết quả. Hàm này quan sát thời gian thực hiện `call()` đồng bộ; nếu `call()` chỉ tạo một future rồi trả về, nó chưa bao trọn công việc chạy trong future.

Các mẫu này giả định custom handler hoạt động bình thường. Callback quan sát có mã người dùng nên cũng có thể ném lỗi; không xem `finally` là lời hứa rằng mọi lỗi từ handler đều được framework vô hiệu hóa. Trong handler riêng, tránh thao tác dễ chặn lâu hoặc làm hỏng luồng nghiệp vụ.

## 4. Dùng observe để quản lý trọn công việc đồng bộ

Khi toàn bộ công việc nằm trong một lambda đồng bộ, thường có thể viết gọn:

```java
Observation.createNotStarted("orders.process", registry)
        .lowCardinalityKeyValue("channel", "web")
        .observe(() -> processOrder());
```

API bao công việc quản lý bắt đầu, scope, báo lỗi thoát ra từ lambda và kết thúc. Không bọc cùng observation bằng cả mẫu thủ công rồi lại gọi `observe`.

Với lambda có kết quả trả về, có thể dùng overload nhận supplier. Ví dụ độc lập về ý tưởng trả kết quả:

```java
int accepted = Observation.createNotStarted("orders.count", registry)
        .observe(() -> 3);
```

Giá trị `3` đến từ công việc, không phải số lần observation đã chạy. Nếu lambda ném ngoại lệ, `observe` không tự biến nó thành giá trị mặc định thành công.

Đối với `observe(Runnable)` của Micrometer 1.13.0 trong chương trình kiểm chứng bên dưới, đường lỗi được quan sát là:

```text
start → open scope → thực thi
                        |
                    ném ngoại lệ
                        v
close scope → error → stop → ngoại lệ đi ra ngoài observe
```

Không biến thứ tự của một overload/phiên bản thành quy tắc bắt buộc cho mọi instrumentation. Điều cần giữ là scope được khôi phục, observation được kết thúc và lỗi nghiệp vụ không bị nuốt ngoài ý muốn.

Các cách gọi tường minh và cách bao bằng `observe` đều được minh họa trong [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

## 5. Chương trình Java kiểm chứng vòng đời

Chương trình thực hiện bốn tình huống:

1. Quản lý thủ công và thành công.
2. Quản lý thủ công và ném lỗi.
3. Dùng `observe(Runnable)` và ném lỗi.
4. Observation cha/con có scope lồng nhau.

Handler chỉ in mốc vòng đời để người học thấy thứ tự, không tạo hệ thống giám sát hay endpoint HTTP.

### 5.1. Chuẩn bị thư viện

Cần JDK 17 trở lên. Với ví dụ độc lập này, đặt hai JAR cùng phiên bản vào thư mục `lib/`:

```text
io.micrometer:micrometer-observation:1.13.0
io.micrometer:micrometer-commons:1.13.0
```

Có thể lấy thư viện từ Maven Central hoặc cache của công cụ build. Phiên bản cố định giúp tái lập stdout của bài; trong ứng dụng Spring Boot, dùng phiên bản được dependency management của Boot quản lý.

Cấu trúc:

```text
lifecycle-demo/
├── ObservationLifecycleDemo.java
└── lib/
    ├── micrometer-observation-1.13.0.jar
    └── micrometer-commons-1.13.0.jar
```

### 5.2. Mã nguồn đầy đủ

Lưu với tên `ObservationLifecycleDemo.java`:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationLifecycleDemo {
    static final class LifecyclePrinter
            implements ObservationHandler<Observation.Context> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            System.out.println("START " + context.getName());
        }

        @Override
        public void onScopeOpened(Observation.Context context) {
            System.out.println("OPEN " + context.getName());
        }

        @Override
        public void onScopeClosed(Observation.Context context) {
            System.out.println("CLOSE " + context.getName());
        }

        @Override
        public void onError(Observation.Context context) {
            System.out.println("ERROR " + context.getName()
                    + " type=" + context.getError().getClass().getSimpleName());
        }

        @Override
        public void onStop(Observation.Context context) {
            String error = context.getError() == null
                    ? "none" : context.getError().getClass().getSimpleName();
            System.out.println("STOP " + context.getName() + " error=" + error);
        }
    }

    static String currentName(ObservationRegistry registry) {
        Observation current = registry.getCurrentObservation();
        return current == null ? "none" : current.getContext().getName();
    }

    static void manual(ObservationRegistry registry, boolean fail) {
        String name = fail ? "manual.failure" : "manual.success";
        Observation observation = Observation.createNotStarted(name, registry);
        System.out.println("CREATED current=" + currentName(registry));
        observation.start();
        System.out.println("AFTER_START current=" + currentName(registry));
        try (Observation.Scope scope = observation.openScope()) {
            System.out.println("BODY current=" + currentName(registry));
            if (fail) {
                throw new IllegalStateException("manual failed");
            }
        }
        catch (RuntimeException | Error ex) {
            observation.error(ex);
            System.out.println("AFTER_ERROR current=" + currentName(registry));
            throw ex;
        }
        finally {
            observation.stop();
        }
    }

    static void automatic(ObservationRegistry registry) {
        Observation observation =
                Observation.createNotStarted("automatic.failure", registry);
        Runnable work = () -> {
            System.out.println("BODY current=" + currentName(registry));
            throw new IllegalArgumentException("automatic failed");
        };
        observation.observe(work);
    }

    static void nested(ObservationRegistry registry) {
        Observation parent = Observation.start("parent", registry);
        try (Observation.Scope parentScope = parent.openScope()) {
            System.out.println("PARENT current=" + currentName(registry));
            Observation child = Observation.start("child", registry);
            try (Observation.Scope childScope = child.openScope()) {
                boolean parentMatches =
                        child.getContext().getParentObservation() == parent;
                System.out.println("CHILD current=" + currentName(registry)
                        + " parentMatches=" + parentMatches);
            }
            finally {
                child.stop();
            }
            System.out.println("RESTORED current=" + currentName(registry));
        }
        finally {
            parent.stop();
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig()
                .observationHandler(new LifecyclePrinter());

        System.out.println("CASE manual.success");
        manual(registry, false);
        System.out.println("AFTER current=" + currentName(registry));

        System.out.println("CASE manual.failure");
        try {
            manual(registry, true);
        }
        catch (IllegalStateException ex) {
            System.out.println("CAUGHT " + ex.getMessage());
        }
        System.out.println("AFTER current=" + currentName(registry));

        System.out.println("CASE automatic.failure");
        try {
            automatic(registry);
        }
        catch (IllegalArgumentException ex) {
            System.out.println("CAUGHT " + ex.getMessage());
        }
        System.out.println("AFTER current=" + currentName(registry));

        System.out.println("CASE nested");
        nested(registry);
        System.out.println("AFTER current=" + currentName(registry));
    }
}
```

Trong ví dụ, handler hỗ trợ `Observation.Context` chung và chấp nhận mọi context của registry thực hành. Một handler chuyên biệt trong ứng dụng thật có thể cần điều kiện hỗ trợ hẹp hơn.

### 5.3. Lệnh chạy

Trong PowerShell tại thư mục chứa file:

```powershell
javac --release 17 -cp "lib/*" ObservationLifecycleDemo.java
java -cp ".;lib/*" ObservationLifecycleDemo
```

Trên Linux/macOS, thay dấu phân cách classpath khi chạy bằng `:`:

```bash
javac --release 17 -cp "lib/*" ObservationLifecycleDemo.java
java -cp ".:lib/*" ObservationLifecycleDemo
```

Chương trình đã được biên dịch với `--release 17` và chạy trên OpenJDK 24.0.2 cùng Micrometer 1.13.0. Stdout thu được:

```text
CASE manual.success
CREATED current=none
START manual.success
AFTER_START current=none
OPEN manual.success
BODY current=manual.success
CLOSE manual.success
STOP manual.success error=none
AFTER current=none
CASE manual.failure
CREATED current=none
START manual.failure
AFTER_START current=none
OPEN manual.failure
BODY current=manual.failure
CLOSE manual.failure
ERROR manual.failure type=IllegalStateException
AFTER_ERROR current=none
STOP manual.failure error=IllegalStateException
CAUGHT manual failed
AFTER current=none
CASE automatic.failure
START automatic.failure
OPEN automatic.failure
BODY current=automatic.failure
CLOSE automatic.failure
ERROR automatic.failure type=IllegalArgumentException
STOP automatic.failure error=IllegalArgumentException
CAUGHT automatic failed
AFTER current=none
CASE nested
START parent
OPEN parent
PARENT current=parent
START child
OPEN child
CHILD current=child parentMatches=true
CLOSE child
STOP child error=none
RESTORED current=parent
CLOSE parent
STOP parent error=none
AFTER current=none
```

### 5.4. Phân tích đường thành công

`CREATED current=none` xuất hiện trước callback `START`: tạo chưa bắt đầu và bắt đầu là hai bước khác nhau.

`AFTER_START current=none` xác nhận observation đã bắt đầu nhưng chưa ở trong scope. Dòng `BODY current=manual.success` chỉ xuất hiện sau `OPEN`.

Khi nghiệp vụ kết thúc, scope được đóng trước khi `finally` dừng observation. Dòng cuối của tình huống là `AFTER current=none`, cho thấy scope không còn bị giữ lại.

Không có callback `ERROR` cho nhánh thành công.

### 5.5. Phân tích đường lỗi thủ công

Lỗi phát sinh trong khối tài nguyên. Vì catch ở ngoài khối đó, thứ tự là:

```text
CLOSE manual.failure
ERROR manual.failure type=IllegalStateException
AFTER_ERROR current=none
STOP manual.failure error=IllegalStateException
CAUGHT manual failed
```

Dòng `AFTER_ERROR` được in ngay sau `observation.error(ex)`. Nó là bằng chứng lời gọi báo lỗi không tự ném lại exception hay kết thúc observation; luồng còn đi tiếp cho đến `throw ex` và `finally`.

Dòng `STOP` chứng minh đường lỗi vẫn đi qua nơi kết thúc observation. Dòng `CAUGHT` đến từ bên gọi, sau cleanup, cho thấy nghiệp vụ thất bại vẫn được truyền ra ngoài.

### 5.6. Phân tích observe và scope lồng nhau

Ở tình huống `automatic.failure`, mã ứng dụng chỉ gọi `observe(work)`; API bao công việc tạo chuỗi callback và đưa lỗi trở lại bên gọi. Với phiên bản được kiểm chứng, `CLOSE` cũng xuất hiện trước `ERROR`.

Ở tình huống lồng nhau:

- Khi parent mở scope, current là `parent`.
- Child được tạo/bắt đầu trong scope đó; `parentMatches=true` xác nhận quan hệ cha của child trong ví dụ.
- Khi child mở scope, current là `child`.
- Sau khi scope con đóng, `RESTORED current=parent`.
- Khi scope cha đóng và observation cha dừng, current trở về `none`.

Hai observation vẫn có hai cặp `START/STOP` riêng. Việc child kết thúc không được làm parent kết thúc sớm.

## 6. Quản lý scope đúng ranh giới thực thi

### 6.1. Scope là tài nguyên phải có chủ sở hữu

Khi nhận một `Observation.Scope` từ `openScope()`, đoạn mã mở nó cần đảm bảo đóng nó tại cuối phạm vi tương ứng. Với thực thi đồng bộ, try-with-resources là lựa chọn dễ kiểm tra.

Đoạn sau là ví dụ **sai do bỏ quên tài nguyên**:

```java
observation.openScope();
processOrder();
observation.stop();
```

Không giữ tài nguyên scope nên đoạn mã không có nơi đóng nó. `stop()` không chữa được thiếu sót này. Trong phép kiểm chứng riêng với Micrometer 1.13.0, sau khi gọi `stop()` bên trong một scope còn mở, registry vẫn trả về observation đó là current; chỉ khi đóng scope thì current trước đó mới được khôi phục.

Hệ quả: đừng suy luận rằng observation đã dừng thì không thể còn làm ô nhiễm phạm vi của luồng.

### 6.2. Đóng theo thứ tự ngược với mở

Với scope cha và con, cấu trúc an toàn về ý nghĩa là:

```text
mở cha
    mở con
        thực thi con
    đóng con
    tiếp tục cha
đóng cha
```

Đóng scope cha khi scope con vẫn đang hoạt động làm sai cấu trúc lồng nhau. Không dựa vào chi tiết một phiên bản có cảnh báo, tự khôi phục hay tiếp tục chạy để coi cách sử dụng đó là hợp lệ.

Try-with-resources lồng nhau thể hiện trực tiếp thứ tự cần tuân thủ.

### 6.3. Một observation có thể được đưa vào nhiều phạm vi thực thi riêng

Một công việc có thể tồn tại lâu hơn một đoạn mã đang chạy trên một luồng. Khi đó, việc đưa observation vào scope trong từng đoạn thực thi và việc kết thúc toàn bộ observation không nhất thiết xảy ra cùng một lúc.

Điều này không cho phép chia sẻ tùy tiện một đối tượng scope giữa các luồng. Mỗi scope phải gắn với phạm vi thực thi thực tế mà nó quản lý, được mở/đóng đúng nơi; observation chỉ được kết thúc khi công việc theo ranh giới đã định thực sự hoàn tất.

Trong bài thực hành đồng bộ, mỗi observation chỉ cần một scope. Với executor/reactive, nên dùng instrumentation và cơ chế truyền ngữ cảnh đã được thiết kế cho mô hình đó, thay vì tự kéo dài một scope của luồng gọi.

## 7. Quy tắc ghi nhận lỗi

### 7.1. Lỗi thoát khỏi lambda và lỗi được xử lý bên trong khác nhau

Nếu exception thoát khỏi lambda của `observe`, API bao công việc có cơ hội ghi nhận nó và ném lại.

Nhưng nếu lambda tự bắt exception rồi trả về bình thường, API bao ngoài không thể biết ứng dụng đã coi sự kiện đó là thất bại hay đã khôi phục thành công.

Ví dụ đoạn trích:

```java
Observation observation =
        Observation.createNotStarted("orders.process", registry);

observation.observe(() -> {
    try {
        processOrder();
    }
    catch (IllegalStateException ex) {
        observation.error(ex);
        useBusinessFallback();
    }
});
```

`processOrder()` và `useBusinessFallback()` là các phương thức của ứng dụng. Đây là ví dụ về việc **chủ động đánh dấu có lỗi dù phương thức có thể hoàn tất bằng một phương án dự phòng**, không phải chính sách bắt buộc cho mọi hệ thống.

Nếu phương án dự phòng là kết quả được mong đợi và không nên tính thành lỗi của thao tác tổng thể, có thể cần một observation con cho lần thử thất bại hoặc metadata kết quả phù hợp. Quyết định này phải dựa trên câu hỏi đang đo, tránh làm tỷ lệ lỗi mất ý nghĩa.

### 7.2. Báo lỗi ở một nơi chịu trách nhiệm

Đừng báo cùng một exception nhiều lần cho cùng observation chỉ vì nó đi qua nhiều catch. Mỗi lời gọi `error(ex)` có thể làm handler phản ứng thêm một lần.

Nếu đã để `observe` quản lý lỗi thoát ra, không cần catch bên trong chỉ để gọi `error` rồi ném lại đúng lỗi đó, trừ khi có một hợp đồng cụ thể được kiểm chứng. Một nơi sở hữu báo lỗi giúp tránh callback lặp.

Một lỗi có thể được ghi ở observation con và ở observation cha khi nó làm cả hai công việc thất bại. Đó là hai phạm vi đo khác nhau, cần phân biệt với việc báo lặp trên cùng một đối tượng.

### 7.3. Không sửa nghiệp vụ để phục vụ telemetry

`observation.error(ex)` không thay cho rollback. `stop()` không commit giao dịch. Đóng scope không bắt exception cho bên gọi.

Các việc này thuộc những cơ chế khác nhau. Mã quan sát cần phản ánh đúng đường đi nghiệp vụ, giữ kết quả trả về và ngoại lệ theo hợp đồng ban đầu.

Cũng không đưa thao tác nghiệp vụ thiết yếu vào handler hoặc context supplier với giả định chúng luôn chạy: observation có thể bị vô hiệu hóa hoặc trở thành no-op. Phần công việc cần được gọi phải nằm trong đường thực thi nghiệp vụ, không phụ thuộc việc có bộ xử lý telemetry.

## 8. Một nơi sở hữu start/stop cho mỗi observation

| Nguồn tạo observation | Ai sở hữu vòng đời? | Mã bên trong nên làm gì? |
| --- | --- | --- |
| Framework đã bao HTTP request | Instrumentation của framework | Dùng scope hiện hành hoặc tạo observation con có ý nghĩa |
| Phương thức tự tạo observation và quản lý thủ công | Phương thức/tiện ích đã bắt đầu nó | Báo lỗi, đóng scope của mình, dừng đúng observation đó |
| Lời gọi `createNotStarted(...).observe(...)` | API bao công việc | Chạy công việc; tránh start/stop thêm cho cùng đối tượng |
| Tác vụ bất đồng bộ tùy biến | Thành phần hiểu điểm hoàn tất thực tế | Định nghĩa rõ nơi bắt đầu, kết thúc và các scope khi chạy |

Không dừng observation lấy từ `registry.getCurrentObservation()` chỉ vì một phương thức con đã xong. Current có thể là HTTP request hoặc công việc cha còn đang chạy.

Cũng không tái sử dụng một observation đã kết thúc cho đơn hàng tiếp theo. Mỗi lần thực hiện là một vòng đời và context riêng; registry có thể dùng chung, observation thì phải phản ánh đúng lần công việc.

Không dùng giả định “gọi stop hai lần chắc không sao” làm cách phối hợp giữa nhiều lớp. Một phiên bản có thể tránh xử lý lặp ở một số đường, nhưng thiết kế dễ kiểm tra vẫn là một nơi chịu trách nhiệm kết thúc, một lần theo ranh giới công việc.

## 9. Khi chuyển sang bất đồng bộ, phải đổi cách xác định kết thúc

Đây là một ví dụ **đo sai ranh giới nếu mục tiêu là toàn bộ công việc trong future**:

```java
CompletableFuture<Order> future =
        Observation.createNotStarted("orders.async", registry)
                .observe(() -> submitOrderAsync());
```

Đoạn trích giả định ứng dụng có kiểu `Order` và hàm `submitOrderAsync()` trả về `CompletableFuture<Order>`. Nó không phải chương trình chạy độc lập.

Lambda có thể chỉ gửi công việc sang executor rồi trả về future ngay. `observe` đồng bộ kết thúc theo lúc lambda trả về, không tự đợi future hoàn tất. Vì thế:

- Khoảng được đo có thể chỉ là thời gian gửi tác vụ.
- Lỗi xảy ra sau đó trong future không tự trở thành exception thoát ra từ lambda đã hoàn tất.
- Scope của luồng gửi không tự tồn tại hợp lệ trên luồng chạy tác vụ.

Nếu mục tiêu chỉ là đo thời gian gửi tác vụ, ranh giới đó có thể phù hợp nhưng cần đặt tên/diễn giải đúng. Nếu mục tiêu là xử lý đơn hàng đến khi hoàn tất, phải dùng cơ chế quan sát hiểu điểm hoàn tất đó.

Khi tự thiết kế, cần trả lời đủ:

1. Observation bắt đầu khi gửi hay khi tác vụ thực sự bắt đầu?
2. Nếu executor từ chối tác vụ ngay, ai báo lỗi và kết thúc?
3. Khi tác vụ hoàn tất thành công hoặc thất bại, ai kết thúc đúng một lần?
4. Khi hủy tác vụ, ranh giới nghiệp vụ đã kết thúc chưa, hay công việc nền vẫn tiếp tục?
5. Scope được mở/đóng ở đâu trên từng luồng đang chạy?
6. Quan hệ với observation cha được truyền bằng cơ chế nào?

Tạo observation và truyền ngữ cảnh là hai bài toán liên quan nhưng riêng biệt. Xem [Micrometer Observation — Instrumentation](https://docs.micrometer.io/micrometer/reference/1.13/observation/instrumenting.html).

Với reactive publisher, cần gắn vòng đời với subscription và các tín hiệu kết thúc theo instrumentation phù hợp. Mở scope quanh thời điểm dựng publisher không có nghĩa scope ấy bao trọn lần xử lý về sau. Không dùng `block()` hoặc `join()` chỉ để ép mô hình đồng bộ mà bỏ qua yêu cầu về luồng của ứng dụng.

## 10. Áp dụng trong Spring Boot Actuator

Trong ứng dụng Spring Boot 3.3 có auto-configuration quan sát phù hợp, inject registry do Spring quản lý thay vì tạo một registry riêng trong mỗi phương thức.

Ví dụ đoạn constructor:

```java
public OrderService(ObservationRegistry observationRegistry) {
    this.observationRegistry = observationRegistry;
}
```

Đây là đoạn trích trong service đã có trường tương ứng. Registry được dùng chung; observation được tạo theo từng lần thực hiện.

Spring Boot đăng ký các bean `ObservationHandler` phù hợp vào registry được quản lý. Nhưng đăng ký handler không chuyển quyền sở hữu vòng đời của một observation từ framework sang mọi service sử dụng registry. Ranh giới start/stop vẫn phải theo nơi tạo và quản lý observation.

Nếu một yêu cầu HTTP đã được instrument, có thể tạo observation con cho công việc nghiệp vụ riêng như xử lý đơn hàng. Tránh bọc lại cùng ranh giới nhiều lần chỉ để tạo thêm số liệu.

Tích hợp của Boot và việc truyền current observation qua luồng/reactive phụ thuộc cấu hình cùng thư viện liên quan; xem [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Chương trình console của bài không cần expose endpoint Actuator. Nó kiểm chứng vòng đời tại API; việc xem metrics/traces trên backend là bước xác minh đầu ra riêng sau khi đã có tích hợp tương ứng.

## 11. Các lỗi thường gặp

| Biểu hiện | Thiếu sót thường gặp | Cách sửa về cấu trúc |
| --- | --- | --- |
| Lỗi nghiệp vụ làm mất callback stop | Đặt stop sau công việc mà không có finally | Đưa kết thúc vào nơi luôn chạy hoặc dùng API bao công việc |
| Đã start nhưng current không phải observation mong muốn | Chưa mở scope | Mở scope đúng phạm vi thực thi |
| Đã stop nhưng luồng vẫn có current cũ | Scope chưa đóng | Quản lý tài nguyên scope; đừng dùng stop để thay close |
| Observation cha bị mất khi hàm con xong | Tự xóa current hoặc đóng sai thứ tự | Khôi phục scope trước đó bằng cấu trúc lồng đúng |
| Có exception nhưng callback lỗi không chạy | Tự bắt lỗi hoặc quản lý thủ công mà không báo | Xác định nơi chịu trách nhiệm error theo hợp đồng |
| Callback lỗi chạy nhiều lần | Báo lỗi thủ công rồi lại để wrapper báo cùng lỗi | Chọn một nơi báo lỗi cho cùng observation |
| Observation kết thúc quá sớm | Lambda chỉ trả về future/publisher | Chọn cơ chế gắn với điểm hoàn tất thực tế |
| Có số liệu lặp | Start/stop hoặc instrumentation bị bao lặp | Kiểm kê nơi sở hữu vòng đời và ranh giới công việc |
| Service con làm HTTP observation kết thúc | Dừng current observation của framework | Chỉ dừng observation do chính mình sở hữu |
| Các yêu cầu lẫn ngữ cảnh | Giữ scope/context của lần trước | Tạo observation/context riêng, đóng scope đúng hạn |

## 12. Tự kiểm tra bằng tình huống

**Tình huống 1:** Phương thức gọi `start()`, nghiệp vụ chạy xong, nhưng phương thức con không thấy current observation. Có thể kết luận start không chạy không?

Không. Start và scope là hai trục khác nhau. Kiểm tra đã mở scope trên luồng thực sự chạy phương thức con hay chưa.

**Tình huống 2:** Mã chỉ gọi `observation.error(ex)` rồi `return`. Observation có tự dừng không?

Không nên suy ra như vậy. Báo lỗi không thay cho kết thúc. Phải có nơi dừng vòng đời, thường là `finally` của đoạn quản lý thủ công hoặc wrapper phù hợp.

**Tình huống 3:** Scope con đã đóng, registry trả lại observation cha. Đây có phải rò rỉ scope không?

Chưa thể coi là rò rỉ. Nếu cha vẫn đang ở trong scope, đó là khôi phục đúng. Kiểm tra theo phạm vi trước khi mở con, không đặt điều kiện mọi close phải làm current thành `null`.

**Tình huống 4:** `observe` đã xong nhưng future mới xử lý được một nửa. API có sai không?

Chưa chắc. Lambda đồng bộ có thể đã hoàn tất việc gửi tác vụ. Muốn quan sát toàn bộ công việc nền thì phải chọn ranh giới và cơ chế kết thúc khác.

**Thực hành thêm với chương trình mẫu:**

- Thay lỗi thủ công bằng một lần trả về sớm và kiểm tra vẫn có `CLOSE`, `STOP`.
- Di chuyển catch báo lỗi vào trong scope, dự đoán rồi kiểm tra vị trí `ERROR` so với `CLOSE`.
- Giữ observation cha mở, chạy hai observation con tuần tự và kiểm tra current trở lại cha sau mỗi con.
- Khi kiểm thử tự động, kiểm tra đủ đường thành công, ngoại lệ và không còn scope ngoài dự kiến; không chỉ kiểm tra có một dòng `START`.

Một vòng đời được quản lý đúng phải cho biết ai bắt đầu, đoạn nào đưa observation vào scope, ai báo lỗi và ai kết thúc. Kiểm chứng đủ các đường thoát giúp số liệu phản ánh đúng công việc và ngữ cảnh được khôi phục cho lần thực hiện tiếp theo.
