# Trả null hoặc giá trị mặc định sau lỗi mà hợp đồng không nói rõ

## 1. Vấn đề: một giá trị “bình thường” có thể che một thất bại

Trong Java, khi một đoạn code bắt exception rồi trả `null`, `false`, `0`, chuỗi rỗng, danh sách rỗng, `Optional.empty()` hoặc một object mặc định, người gọi chỉ nhìn thấy **giá trị trả về**, không nhất thiết biết rằng việc thực thi đã thất bại.

Ví dụ:

~~~java
String loadUserName(String id) {
    try {
        return repository.findName(id);
    } catch (RuntimeException ignored) {
        return null;
    }
}
~~~

Đây là **fragment minh họa không độc lập**; `repository` chưa được định nghĩa. Nếu `findName` vốn trả `null` khi không có người dùng, thì cả hai tình huống sau trở nên không phân biệt được:

1. Truy vấn thành công, nhưng người dùng thật sự không tồn tại.
2. Truy vấn không thực hiện được vì database mất kết nối, sai cấu hình hoặc code ném exception.

Một caller có thể viết `if (name == null) return 404;`, khiến lỗi hạ tầng bị trình bày thành “người dùng không tồn tại”. Hậu quả có thể là trả thông báo sai, kích hoạt tạo bản ghi trùng, cache một kết quả âm giả hoặc bỏ qua một lỗi cần retry.

**Sai lầm cốt lõi không chỉ là việc trả `null`.** Vấn đề là **API không định nghĩa rõ khi nào giá trị đó hợp lệ, có nghĩa gì và liệu exception đã xảy ra hay không**. Một giá trị mặc định chỉ an toàn khi hợp đồng nêu điều kiện sử dụng và caller có thể phân biệt hoặc chấp nhận hệ quả của fallback.

Mục tiêu bài học:
- Phân biệt **thành công có dữ liệu**, **thành công nhưng không có dữ liệu**, **thất bại**, **hủy/quá hạn** và **fallback có chủ đích**.
- Biết vì sao `null`, `Optional.empty()`, `0`, `false`, `""` và collection rỗng không phải thông báo lỗi tổng quát.
- Chọn khi nào nên **truyền exception**, khi nào trả **result có kiểu**, và khi nào fallback là đúng hợp đồng.
- Giữ `cause`, mã lỗi và khả năng quan sát, không biến một sự cố nghiêm trọng thành “success”.
- Kiểm thử đường thất bại bằng fault injection, kể cả side effect đã xảy ra trước exception.

## 2. Phân loại kết cục trước khi thiết kế kiểu trả về

Một thao tác bất kỳ có thể rơi vào những nhóm sau:

| Kết cục | Ví dụ | Ý nghĩa cần truyền |
| --- | --- | --- |
| Thành công có kết quả | Tìm thấy khách hàng `A` | `Found(customer)` |
| Thành công không có kết quả | ID hợp lệ, truy vấn xong và không có bản ghi | `NotFound(id)` hoặc `Optional.empty()` theo contract |
| Từ chối nghiệp vụ dự kiến | Đơn hàng vi phạm hạn mức | `Rejected(reason)` hoặc exception nghiệp vụ đã định nghĩa |
| Lỗi thực thi | Database timeout, đọc file lỗi, bug trong callback | Exception hoặc `Failed(code, cause)` |
| Quá hạn chờ | Caller không nhận kết quả trước deadline | `TimeoutException`/`PENDING`/`UNKNOWN` theo phạm vi |
| Hủy | Tác vụ bị hủy theo yêu cầu | `Cancelled` hoặc `CancellationException` theo API |
| Fallback có kiểm soát | Dùng bản cache cũ khi nguồn chính lỗi, được policy cho phép | `Fallback(value, source, age)` hoặc metadata tương đương |

Một API không nhất thiết cần bảy class cho bảy trạng thái. Nhưng **phải trả lời được câu hỏi mỗi giá trị có ý nghĩa gì**, và trạng thái nào được phân biệt với trạng thái nào.

Ví dụ `Optional<User> findById(String id) throws IOException` là một hợp đồng tương đối rõ: nếu truy vấn thành công, trả `Optional.of(user)` hoặc `Optional.empty()`; nếu nguồn dữ liệu không đọc được, ném `IOException`. Trái lại, `Optional.empty()` cho cả “không thấy” và “không kết nối DB” làm `Optional` mất ý nghĩa.

### 2.1. Không có giá trị khác với không biết giá trị

Có một khác biệt rất lớn:

- **Không có:** hệ thống đã kiểm tra thành công và xác nhận không có bản ghi.
- **Không biết:** hệ thống chưa kiểm tra được do lỗi, timeout hoặc dữ liệu chưa đồng bộ.

`null`/`Optional.empty()` thường chỉ phù hợp với trường hợp thứ nhất khi hợp đồng xác định như vậy. Trường hợp thứ hai cần trạng thái lỗi/unknown hoặc cơ chế retry/đối soát. Nếu không phân biệt, caller có thể quyết định sai dù không có exception nào xuất hiện trong log.

## 3. Vì sao catch rồi trả `null` đặc biệt khó chẩn đoán?

~~~java
User getUser(String id) {
    try {
        return database.load(id);
    } catch (Exception e) {
        return null;
    }
}
~~~

Đây là fragment, `User`/`database` chưa định nghĩa. Việc catch rộng rồi trả `null` có ít nhất bốn nguy cơ:

1. **Nuốt nguyên nhân:** `IOException`, `SQLException`, `IllegalStateException` và lỗi lập trình khác đều bị ép thành một trạng thái `null`.
2. **Tạo exception thứ cấp:** code phía trên truy cập `user.getName()` và nhận `NullPointerException` ở nơi xa lỗi ban đầu; trace chỉ tới việc dereference `null`, không còn cause gốc.
3. **Giả thành công:** phương thức kết thúc bình thường và metric tự động có thể đánh dấu success dù dependency đã thất bại.
4. **Làm sai quy trình nghiệp vụ:** caller coi null là “chưa có dữ liệu” rồi tạo mới/ghi cache/ra quyết định không chính xác.

Việc đổi thành `catch (IOException e) { return null; }` có giảm độ rộng catch nhưng **vẫn làm mất trạng thái lỗi I/O** nếu hợp đồng không nêu rõ null cũng đại diện cho lỗi. Một comment như `// ignore` không phải điều kiện bảo đảm an toàn.

### 3.1. `null` có thể hợp lệ khi nào?

`null` có thể là giá trị được định nghĩa hợp pháp trong một số API legacy, framework binding hoặc giao thức dữ liệu. Khi đó tài liệu phải nêu rõ:
- Điều kiện nào làm hàm trả `null`?
- `null` là dữ liệu hợp lệ, không tìm thấy, chưa tải hay lỗi?
- Nếu operation thật sự thất bại, caller nhận exception hay trạng thái nào?
- Những lệnh có side effect trước khi trả null có thể đã được thực hiện chưa?
- Có annotation/nullability tooling và test xác minh contract không?

Một API công khai `@Nullable User find(String id)` có thể nêu null = không tồn tại; vậy lỗi database phải đi qua kênh khác, không được cũng trả null. Nullability annotation giúp diễn đạt **giá trị có thể null**, nhưng tự nó không nói hết ý nghĩa nghiệp vụ của null.

## 4. `false`, `0`, `""` và collection rỗng cũng có thể che lỗi

`null` chỉ là một trong các cách biến exception thành dữ liệu bình thường.

| Giá trị mặc định | Tình huống hợp lệ | Sự cố nếu cũng dùng nó khi lỗi |
| --- | --- | --- |
| `false` | Kiểm tra điều kiện và điều kiện không thỏa | Không phân biệt “không được phép” với “service kiểm tra quyền đã lỗi” |
| `0` | Tổng số bản ghi bằng 0, giá tiền hợp lệ bằng 0 | Lỗi tính tiền/đọc số liệu bị hiểu là giá trị 0 thật |
| `""` | Chuỗi nhập trống nhưng hợp lệ | Mất khả năng phân biệt lỗi tải dữ liệu |
| `List.of()` | Truy vấn thành công, danh sách không có phần tử | API đưa ra “không có dữ liệu” khi database không thể truy vấn |
| `Map.of()` | Cấu hình hợp lệ nhưng không có override | Lỗi đọc cấu hình làm ứng dụng bỏ qua chính sách quan trọng |
| `Optional.empty()` | Tìm kiếm hợp lệ không thấy giá trị | Lỗi thực thi bị giả thành absence |
| Object mặc định | Người dùng cố ý chọn thông số mặc định | Data corruption/deserialize error bị che mất |

Phản ví dụ:

~~~java
int loadAccountBalance(String accountId) {
    try {
        return backend.balance(accountId);
    } catch (RuntimeException ignored) {
        return 0;
    }
}
~~~

Đây là fragment minh họa; `backend` chưa định nghĩa. Trả `0` sau lỗi hạ tầng có thể dẫn tới từ chối sai giao dịch, phát thông báo “hết tiền”, hoặc báo cáo tài chính sai. Nếu domain cho phép tài khoản có số dư đúng bằng 0, giá trị này không còn là một sentinel duy nhất.

Với boolean, `false` đôi khi được chọn theo chính sách “deny by default” khi không thể kiểm tra quyền. Đó có thể là **quyết định bảo mật fail-closed đúng**, nhưng contract nên nêu rằng `false` bao gồm trường hợp không xác minh được, hoặc trả trạng thái `DENIED` và `UNAVAILABLE` riêng để có thể chẩn đoán. Không được coi fail-closed là lý do xóa log/metric sự cố authorization service.

## 5. Ví dụ Java 17 hoàn chỉnh: cùng null cho hai tình huống và cách sửa

Chương trình sau có ba tầng biểu diễn:

- `legacy` mô phỏng API cũ: trả `null` cho cả “không thấy” và lỗi I/O.
- `findOptional` trả `Optional.empty()` chỉ khi truy vấn **thật sự hoàn thành** mà không thấy dữ liệu, còn `IOException` được truyền ra.
- `lookup` trả một **sealed result type** gồm `Found`, `Missing` và `Failed`, phân biệt rõ các kết cục.
- `lookupWithCache` minh họa fallback có chủ đích và được dán nhãn riêng `Fallback`; giá trị cache ở đây là giả lập để kiểm chứng phân loại, không phải cache production.

Lưu thành file **`ExplicitFailureResultDemo.java`**:

~~~java
import java.io.IOException;
import java.util.Optional;

public class ExplicitFailureResultDemo {
    sealed interface LookupResult permits Found, Missing, Failed, Fallback {}

    record Found(String key, String value) implements LookupResult {}
    record Missing(String key) implements LookupResult {}
    record Failed(String key, FailureCode code, Throwable cause)
            implements LookupResult {}
    record Fallback(String key, String value, String source)
            implements LookupResult {}

    enum FailureCode { STORAGE_UNAVAILABLE }

    static String fetch(String key) throws IOException {
        return switch (key) {
            case "A" -> "Alice";
            case "B" -> null;
            case "DB_DOWN" -> throw new IOException("database unavailable");
            default -> null;
        };
    }

    static String legacy(String key) {
        try {
            return fetch(key);
        } catch (IOException ignored) {
            return null;
        }
    }

    static Optional<String> findOptional(String key) throws IOException {
        return Optional.ofNullable(fetch(key));
    }

    static LookupResult lookup(String key) {
        try {
            String value = fetch(key);
            return value == null ? new Missing(key) : new Found(key, value);
        } catch (IOException e) {
            return new Failed(key, FailureCode.STORAGE_UNAVAILABLE, e);
        }
    }

    static LookupResult lookupWithCache(String key) {
        LookupResult result = lookup(key);
        if (result instanceof Failed && key.equals("DB_DOWN")) {
            return new Fallback(key, "stale Alice", "cache");
        }
        return result;
    }

    static String describe(LookupResult result) {
        if (result instanceof Found found) {
            return "FOUND " + found.key() + "=" + found.value();
        }
        if (result instanceof Missing missing) {
            return "MISSING " + missing.key();
        }
        if (result instanceof Failed failed) {
            return "FAILED " + failed.key() + "=" + failed.code()
                    + " (" + failed.cause().getMessage() + ")";
        }
        if (result instanceof Fallback fallback) {
            return "FALLBACK " + fallback.key() + "=" + fallback.value()
                    + " from " + fallback.source();
        }
        throw new IllegalStateException("Unknown result");
    }

    public static void main(String[] args) {
        System.out.println("legacy missing is null: " + (legacy("B") == null));
        System.out.println("legacy outage is null: " + (legacy("DB_DOWN") == null));
        System.out.println(describe(lookup("A")));
        System.out.println(describe(lookup("B")));
        System.out.println(describe(lookup("DB_DOWN")));
        System.out.println(describe(lookupWithCache("DB_DOWN")));
        try {
            System.out.println("Optional missing empty: " + findOptional("B").isEmpty());
            findOptional("DB_DOWN");
        } catch (IOException e) {
            System.out.println("Optional outage: " + e.getMessage());
        }
    }
}
~~~

Dùng JDK 17 trở lên, đứng trong thư mục chứa file:

~~~bash
javac --release 17 ExplicitFailureResultDemo.java
java ExplicitFailureResultDemo
~~~

Stdout **đã được biên dịch/chạy kiểm chứng**:

~~~text
legacy missing is null: true
legacy outage is null: true
FOUND A=Alice
MISSING B
FAILED DB_DOWN=STORAGE_UNAVAILABLE (database unavailable)
FALLBACK DB_DOWN=stale Alice from cache
Optional missing empty: true
Optional outage: database unavailable
~~~

### 5.1. Giải thích output

- Hai dòng đầu đều `true`: caller nhận cùng `null` trong API legacy, không thể phân biệt vắng mặt với mất kết nối database.
- `FOUND A=Alice`: dữ liệu tồn tại và thao tác thành công.
- `MISSING B`: truy vấn được thực hiện hợp lệ, không có bản ghi.
- `FAILED DB_DOWN=STORAGE_UNAVAILABLE (...)`: lỗi I/O được đưa vào kết quả có kiểu `Failed`, kèm mã ổn định và `cause`.
- `FALLBACK ... from cache`: nhánh fallback là một kết quả **có nhãn**. Caller biết nó không phải dữ liệu tươi từ nguồn chính.
- `Optional missing empty: true`: `Optional.empty()` chỉ mô tả không có giá trị, không bị dùng làm mã lỗi.
- `Optional outage: database unavailable`: lỗi nguồn vẫn đi qua đường `IOException`; caller có thể xử lý/ghi nhận đúng.

Ví dụ đơn giản hóa bằng chuỗi `stale Alice` khi khóa `DB_DOWN` lỗi. Ứng dụng thật phải kiểm tra cache key, phiên bản, thời gian tạo, quyền truy cập và giới hạn staleness trước khi trả fallback. **Không lấy một dữ liệu cache tùy ý cho sai khách hàng** chỉ vì muốn cung cấp giá trị mặc định.

### 5.2. Tại sao dùng sealed interface và record?

Java 17 hỗ trợ `sealed interface` và `record` ổn định, cho phép mô tả những trường hợp kết quả được phép tồn tại:
- `Found` chứa dữ liệu trả về.
- `Missing` chứa khóa không có.
- `Failed` chứa mã lỗi và cause nội bộ.
- `Fallback` chứa giá trị cùng nguồn dự phòng.

Dùng `instanceof` pattern matching trong `describe` giúp phân biệt nhánh rõ ràng mà không cần sentinel `null`. Nếu thêm một loại kết quả khác, cần cập nhật logic xử lý tương ứng. Trong production, có thể lựa chọn sealed hierarchy với các record phong phú hơn, hoặc exception + `Optional` nếu nhu cầu thực sự đơn giản.

**Lưu ý bảo mật:** `Throwable cause` trong record chỉ phù hợp lưu/ghi nhận nội bộ. Không tuần tự hóa stack trace, thông tin kết nối hay dữ liệu nhạy cảm thẳng ra HTTP response hoặc message công khai. Chỉ xuất error code và thông tin an toàn theo hợp đồng API.

## 6. `Optional` không phải một container lỗi tổng quát

`Optional<T>` trong Java được thiết kế để biểu diễn **có hoặc không có một giá trị**. Nó không chứa reason hay cause.

Mẫu đúng nếu `Optional.empty()` = “không tìm thấy”:

~~~java
Optional<String> readName(String id) throws IOException {
    String name = readFromStorage(id);
    return Optional.ofNullable(name);
}
~~~

Đây là fragment, `readFromStorage` chưa khai báo. Nếu storage ném `IOException`, exception truyền ra; không bị tự đổi thành `Optional.empty()`. Với caller, điều đó cho phép:
- `Optional.of(value)`: có dữ liệu.
- `Optional.empty()`: truy vấn hoàn tất nhưng không có dữ liệu.
- `IOException`: không thể hoàn thành truy vấn.

Mẫu sai:

~~~java
Optional<String> readName(String id) {
    try {
        return Optional.ofNullable(readFromStorage(id));
    } catch (IOException ignored) {
        return Optional.empty();
    }
}
~~~

Ở đây `Optional.empty()` vừa chỉ absence vừa che lỗi I/O. Nếu API contract ban đầu không nêu điều này, đây là **thay đổi nghĩa** dữ liệu nguy hiểm.

### 6.1. `orElse` và `orElseGet` không tự phục hồi lỗi ở tầng dưới

Ví dụ:

~~~java
String label = optionalName.orElse("Anonymous");
~~~

Đây là fragment với `optionalName` đã có. `"Anonymous"` được dùng khi Optional rỗng, không phải “bắt mọi exception” từ quá trình tạo `optionalName`. Nếu người viết đã chuyển `IOException` thành Optional rỗng ở tầng dưới, `orElse` sẽ âm thầm tạo một “tên hợp lệ” giả.

Ngoài ra, `orElse(expression)` đánh giá argument theo quy tắc gọi phương thức Java, còn `orElseGet(supplier)` chỉ gọi supplier khi thiếu giá trị. Khác biệt này quan trọng nếu fallback tốn kém hoặc có side effect; nhưng **dùng lazy supplier không sửa được hợp đồng lỗi mơ hồ**.

### 6.2. `Optional.ofNullable` chỉ xem xét null, không biết nguồn null

`Optional.ofNullable(value)` tạo Optional rỗng khi `value == null`. Nó không nhận metadata nói null do “không tồn tại”, “deserialize lỗi”, “dependency không sẵn sàng” hay “lập trình viên đã catch exception”. Nếu hệ thống cần phân biệt nguyên nhân, phải thiết kế thông tin đó **trước bước chuyển sang Optional**.

## 7. `Map.get` và những API có giá trị mặc định riêng

`Map.get(key)` có thể trả `null` trong hai trường hợp:
- Không có mapping cho key.
- Có mapping nhưng value được lưu là `null` (với Map implementation cho phép null).

Với một Map cho phép null, muốn phân biệt có key hay không, dùng `containsKey(key)`:

~~~java
Map<String, String> settings = new HashMap<>();
settings.put("theme", null);
System.out.println(settings.containsKey("theme")); // true
System.out.println(settings.get("theme") == null); // true
~~~

Đây là fragment; cần import `java.util.Map` và `java.util.HashMap`. Đây là **mơ hồ thuộc hợp đồng dữ liệu của Map**, không phải exception. Khi một adapter cache hoặc repository trả null sau exception, độ mơ hồ còn tăng thêm: không chỉ “key không có hay value null”, mà cả “đã truy vấn thành công hay chưa”.

`Map.getOrDefault(key, defaultValue)` trả fallback khi không có mapping; nếu key tồn tại và được map tới null, behavior có thể giữ null. Không dùng `getOrDefault` như cơ chế “thử truy vấn thất bại thì tự khôi phục”; nó chỉ xử lý absence theo semantics của Map.

**Quy tắc:** hiểu sentinel mặc định của collection/API đã có trước khi tận dụng nó làm kênh lỗi mới.

## 8. Khi nào exception là hợp đồng phù hợp?

Không phải lỗi nào cũng cần chuyển thành `Failed` record. Với nhiều API Java, phương thức có thể:
- trả giá trị hợp lệ hoặc absence theo miền nghiệp vụ;
- **ném exception** nếu không thể hoàn thành thao tác.

Ví dụ:

~~~java
Optional<Invoice> findInvoice(String id) throws IOException {
    return invoiceStore.find(id);
}
~~~

Đây là fragment với `Invoice`, `invoiceStore` giả định. Nếu thao tác đọc lỗi, truyền `IOException` giữ kênh lỗi tách biệt. Nếu tầng trên muốn chuyển nó thành HTTP 503 hoặc kết quả `StorageUnavailable`, hãy làm ở ranh giới có khả năng quyết định chính sách.

Nếu exception là kết cục nghiệp vụ dự kiến (ví dụ ID không hợp lệ), có thể dùng checked exception, unchecked domain exception hoặc result type tùy convention hệ thống. Điều quan trọng là **caller có thể nhận biết và test những kết cục đó**.

### 8.1. Rethrow và wrap giữ nguyên cause

Khi không thể xử lý:

~~~java
try {
    return remoteRead();
} catch (IOException e) {
    throw e;
}
~~~

Fragment này giả định phương thức cho phép `throws IOException`. Nếu không thêm xử lý/ngữ cảnh, có thể bỏ try-catch để exception tự lan.

Nếu muốn bọc theo tầng dịch vụ:

~~~java
try {
    return remoteRead();
} catch (IOException e) {
    throw new IllegalStateException("Unable to read report", e);
}
~~~

Đây là fragment, `remoteRead` chưa định nghĩa. Dùng constructor chứa `cause` giúp caller/logging thấy nguyên nhân gốc. Tránh:

~~~java
catch (IOException e) {
    return null;
}
~~~

khi null không phải một nhánh lỗi được định nghĩa. Cũng tránh `throw new IllegalStateException("failed")` không cause vì mất đường trace từ lỗi I/O ban đầu.

### 8.2. Không catch rộng để biến mọi lỗi thành default

~~~java
try {
    return execute();
} catch (Exception e) {
    return defaultResult();
}
~~~

Đây là fragment. `Exception` có thể bao gồm IOException được dự kiến lẫn `NullPointerException`/`IllegalStateException` do bug. Khi dependency thêm một lỗi mới, đoạn catch rộng cũng biến nó thành fallback, làm lỗi lập trình bị che.

`catch (Throwable)` còn bắt các `Error` của JVM, thường không phù hợp để trả giá trị thành công. Ở ranh giới rất đặc biệt có thể bắt rộng để giám sát và shutdown có kiểm soát, nhưng vẫn phải **bảo toàn tín hiệu thất bại**, không mặc định trả success.

## 9. Thiết kế fallback đúng: giá trị, nguồn và độ tin cậy

Fallback là một **quyết định nghiệp vụ**, không phải thói quen của catch. Ví dụ một dashboard đọc dữ liệu thống kê có thể cho phép dùng cache 5 phút khi hệ thống nguồn tạm thời không sẵn sàng. Nhưng API cần mô tả:
- Fallback được phép cho loại lỗi nào?
- Có giá trị cache hợp lệ cho **đúng key/tenant** không?
- Cache cũ tối đa bao lâu? Có trường hợp không được dùng dữ liệu cũ (giá, tồn kho, quyền hạn, giao dịch)?
- Client có cần biết dữ liệu **degraded/stale** không?
- Có metric/log để vận hành biết nguồn chính thất bại không?
- Khi fallback cũng thất bại, caller thấy kết cục gì?
- Có side effect nào trước khi dùng fallback không?

Vì vậy, kiểu:

~~~java
record CachedValue<T>(
        T value,
        String source,
        java.time.Instant fetchedAt,
        boolean stale) {}
~~~

là một **fragment Java 17** có thể mang metadata. Với API trả `CachedValue<T>`, caller không phải suy đoán fallback từ một chuỗi rỗng hoặc null.

### 9.1. Ví dụ cấu hình: “thiếu” khác “sai”

Một cấu hình như `APP_PORT` có thể được định nghĩa:
- Biến môi trường **không có** → dùng giá trị mặc định 8080.
- Có nhưng chứa `"abc"` → cấu hình sai; báo lỗi startup.
- Có `"-1"` → giá trị ngoài miền; báo lỗi.
- Có `"0"` → có thể mang ý nghĩa đặc biệt (ví dụ yêu cầu server chọn ephemeral port) nếu contract cho phép; không nên tự đổi thành 8080.

Anti-pattern:

~~~java
try {
    return Integer.parseInt(rawPort);
} catch (NumberFormatException e) {
    return 8080;
}
~~~

Đây là fragment với `rawPort` giả định. Nó coi **giá trị cấu hình sai** như “không cấu hình”, khiến triển khai chạy sai cổng một cách âm thầm. Có thể chọn default khi *biến thật sự không tồn tại*, rồi kiểm tra giá trị hiện diện theo contract.

### 9.2. Fail-open và fail-closed phải được thể hiện rõ

Với quyết định bảo mật, một API trả `false` sau lỗi đôi khi thực thi chính sách **fail-closed** (từ chối khi không thể xác minh). Đây có thể là quyết định đúng. Nhưng nếu caller xem `false` là “người dùng chắc chắn không có quyền” thay vì “không thể xác minh quyền”, báo cáo và vận hành sẽ sai.

Có thể tách:
- `ALLOWED`;
- `DENIED`;
- `UNAVAILABLE`/`INDETERMINATE`.

Sau đó tầng API áp chính sách fail-closed cho `UNAVAILABLE` nhưng vẫn ghi nhận dependency lỗi. Không chuyển lỗi kiểm tra quyền thành `true` để “dịch vụ không bị gián đoạn”.

## 10. `CompletableFuture.exceptionally` có thể biến lỗi thành “success giả”

Một đoạn async phổ biến:

~~~java
CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> loadRemote())
                .exceptionally(error -> "");
~~~

Đây là **fragment**, `loadRemote()` chưa khai báo. Nếu supplier ném exception, stage mới hoàn thành **bình thường với chuỗi rỗng**. `whenComplete((value, error) -> ...)` đặt phía sau sẽ thấy `error == null`; metric success ở đó có thể tăng dù nguồn đã lỗi.

Với dữ liệu đọc có thể thực sự rỗng, `""` che toàn bộ cause. Một thiết kế rõ ràng hơn là:
- Để exceptional completion truyền tới caller, và xử lý nguyên nhân tại ranh giới phù hợp; hoặc
- Dùng `handle` chuyển cả success/failure thành `Outcome` có kiểu; hoặc
- Dùng `exceptionally` với fallback được **hợp đồng cho phép**, trả kèm metadata bằng kiểu dữ liệu của stage.

### 10.1. Sự khác nhau giữa `handle`, `exceptionally` và `whenComplete`

| API | Tác dụng chính | Bẫy cần tránh |
| --- | --- | --- |
| `exceptionally(fn)` | Tạo giá trị mới khi stage thất bại | Fallback không có nhãn khiến lỗi biến thành success giả |
| `handle((value,error) -> ...)` | Chuyển success/failure thành kết quả mới | Nếu trả object mặc định ở nhánh lỗi mà không mã trạng thái, vẫn mơ hồ |
| `whenComplete((value,error) -> ...)` | Quan sát completion, thường không thay đổi kết quả | Nó không tự “xử lý hết” exception; observer ném lỗi có thể làm stage mới lỗi |
| `thenApply(fn)` | Chuyển đổi giá trị khi upstream thành công | Không được gọi trên nhánh lỗi upstream |
| `get()` / `join()` | Quan sát kết quả và exceptional completion | Nếu task đã tự nuốt lỗi trước đó, không thể biết cause chỉ bằng Future |

Ví dụ typed outcome (fragment, `Outcome`/`Success`/`Failure` giả định có định nghĩa):

~~~java
CompletableFuture<Outcome> observed = source.handle((value, error) ->
        error == null
                ? new Success(value)
                : new Failure("REMOTE_ERROR", error));
~~~

Nếu một stage thành công với `null`, điều kiện `error == null` vẫn biểu thị completion bình thường. Không dùng `value != null` để kết luận success. Với lỗi bọc `CompletionException`, giữ nguyên cause chain hoặc tháo wrapper có kiểm soát; không giả định `error.getCause()` luôn khác null.

### 10.2. Future và executor cũng chịu cùng vấn đề

~~~java
Future<String> task = executor.submit(() -> {
    try {
        return loadRemote();
    } catch (IOException e) {
        return null;
    }
});
~~~

Đây là fragment với `executor` và `loadRemote` giả định. Vì `Callable` đã bắt exception và trả `null` bình thường, `task.get()` cũng có thể trả null, **không ném `ExecutionException`**. Executor không thể tự tái tạo lỗi mà task đã nuốt.

Đừng xem “Future completed normally” đồng nghĩa công việc nghiệp vụ thành công; nếu kiểu T cho phép `Failure`, caller phải kiểm tra trạng thái nghiệp vụ trong T.

## 11. Timeout và cancellation: không phải một giá trị trống bình thường

Nếu `future.get(timeout, unit)` ném `TimeoutException`, điều đó chỉ nói caller **chưa nhận được kết quả trong thời gian chờ**; task có thể vẫn chạy và tạo side effect. Trả `null`/`false`/`List.of()` cho timeout mà không nêu ý nghĩa làm caller dễ hiểu nhầm “không có dữ liệu”.

Ví dụ sai:

~~~java
try {
    return future.get(1, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    return null;
}
~~~

Đây là fragment cần những import/checked exception khác và một phương thức có kiểu trả phù hợp. Chỉ có một “không có kết quả kịp thời” không chứng minh request đã thất bại, bị hủy hoặc chưa xảy ra.

Tùy hệ thống:
- Có thể trả `PENDING(jobId)` và cho phép tra cứu kết quả.
- Có thể trả `UNKNOWN(operationId)` nếu remote side effect chưa thể xác nhận.
- Có thể ném/propagate timeout qua hợp đồng exception.
- Có thể hủy task do caller sở hữu, nếu task hỗ trợ cancellation và nghiệp vụ cho phép.

Cũng không được nuốt `InterruptedException` của thread đang đợi rồi trả giá trị mặc định “thành công”; thường cần truyền tiếp hoặc restore interrupt status và chấm dứt xử lý. `CancellationException` phải được phân loại theo hợp đồng, không biến tất cả cancellation thành dữ liệu rỗng hợp lệ.

## 12. HTTP và JSON: null/empty có thể làm sai giao thức

Khi API server bắt lỗi storage rồi trả response body có field `"user": null` và HTTP 200, client khó phân biệt:
- Người dùng thật sự không tồn tại.
- Người dùng tồn tại nhưng dữ liệu rỗng có chủ đích.
- Backend đọc dữ liệu thất bại.
- Request bị timeout hoặc token thiếu quyền.

Một hợp đồng API rõ hơn có thể chọn:
- HTTP **200** cho dữ liệu tìm thấy/thao tác thành công.
- HTTP **404** cho tài nguyên không tồn tại **sau kiểm tra hợp lệ**.
- HTTP **503** khi backend tạm thời không sẵn sàng.
- HTTP **500** cho lỗi nội bộ bất thường.
- HTTP **202** và job ID cho công việc được nhận nhưng chưa hoàn tất.

Các status là lựa chọn thông thường cần phù hợp semantics của API; không phải quy tắc ép mọi trường hợp. Với endpoint tìm kiếm danh sách, danh sách rỗng có thể là một **200 hợp lệ**; lỗi database không được giả thành danh sách rỗng chỉ để luôn trả HTTP 200.

### 12.1. JSON `null` có thể mang nhiều nghĩa

Trong JSON, cần phân biệt:
- Field **vắng mặt**.
- Field tồn tại và có giá trị `null`.
- Field có chuỗi rỗng `""`.
- Field có mảng `[]` hoặc object `{}`.
- Field có giá trị hợp lệ nhưng mặc định.

Không tự suy rằng serializer sẽ ánh xạ tất cả chúng theo cùng một quy tắc; đó là quyết định của DTO, serialization library và cấu hình. Với API patch/update, `null` có thể mang nghĩa **xóa giá trị**, trong khi field vắng mặt nghĩa **không thay đổi**. Nếu adapter nuốt lỗi rồi tạo DTO với null, bạn có thể vô tình thực hiện thao tác xóa không được yêu cầu.

Một error response có thể chứa mã ổn định, correlation ID và message an toàn; không xuất stack trace, JDBC URL, token hay dữ liệu người dùng ở phía public.

## 13. Database: “không có bản ghi” khác lỗi thực thi truy vấn

Với JDBC:
- `ResultSet.next() == false` sau khi statement được thực thi hợp lệ có thể biểu thị **không còn dòng kết quả**.
- `SQLException` khi chuẩn bị/truy vấn/đọc kết quả báo không hoàn thành theo hợp đồng.
- Connection timeout, transaction timeout và lỗi commit có thể có ngữ nghĩa riêng, đôi khi trạng thái đã thực thi **không chắc chắn**.

Anti-pattern:

~~~java
try {
    return queryCustomer(id);
} catch (SQLException ignored) {
    return null;
}
~~~

Đây là fragment; `queryCustomer` giả định. Nếu null đang có nghĩa “không có khách hàng”, caller có thể tạo một hàng mới vì tưởng ID chưa tồn tại, dù DB đang tạm thời lỗi.

Với giao dịch có side effect, việc nhận lỗi sau commit chưa chắc chứng minh transaction đã rollback. Đừng trả danh sách rỗng, `false` hoặc `UNKNOWN` một cách tùy tiện; chọn đúng trạng thái và biện pháp đối soát khi cần.

### 13.1. Negative caching làm lỗi kéo dài

Một cache có thể lưu kết quả **“không tìm thấy”** để giảm truy vấn lặp. Nhưng nếu một lỗi storage bị chuyển thành `Optional.empty()`, cache có thể lưu absence giả với TTL vài phút; kể cả DB phục hồi, ứng dụng vẫn trả không tồn tại.

Vì vậy nên định nghĩa:
- **Positive cache** cho `Found`.
- **Negative cache** chỉ cho `NotFound` đã xác nhận, thời hạn phù hợp.
- **Không cache như NotFound** các `Failed` hoặc `Unknown`.
- Nếu cache fallback sau lỗi, gắn trạng thái nguồn/degraded và thời hạn riêng.

Mẫu này cho thấy tác hại của default mơ hồ không dừng ở một response; nó có thể lan sang trạng thái cache và ảnh hưởng request về sau.

## 14. Parse/validate: vắng đầu vào khác dữ liệu không hợp lệ

Giả sử đọc cấu hình số lượng worker:

~~~java
int parseWorkers(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException e) {
        return 1;
    }
}
~~~

Đây là fragment hoàn chỉnh về cú pháp nhưng chưa có class bao quanh. Nếu contract “không cấu hình thì mặc định 1”, việc biến chuỗi `"xyz"` thành 1 che lỗi cấu hình. Cách hợp lý hơn:
1. Kiểm tra biến cấu hình **không tồn tại** → dùng 1.
2. Có giá trị → parse; nếu không phải số, ném một exception cấu hình có ngữ cảnh.
3. Kiểm tra phạm vi (ví dụ từ 1 đến 64).
4. Báo lỗi startup hoặc kết quả validation rõ ràng.

Với form người dùng, chuỗi rỗng có thể là input hợp lệ trong một số field, nhưng không thể tự dùng cho lỗi không đọc được body JSON hoặc lỗi encoding nếu contract phân biệt.

`Integer.parseInt` ném `NumberFormatException`; nó không trả 0 khi không parse được. Đừng thêm catch để biến thành 0 trừ khi spec thực sự định nghĩa rõ “parse fail = 0” và caller hiểu chính sách đó.

## 15. Mã lỗi có cấu trúc: thiết kế hợp đồng đủ dùng

Một hierarchy kiểu:

~~~java
sealed interface SaveOutcome
        permits Saved, Rejected, SaveFailed {}

record Saved(String id) implements SaveOutcome {}
record Rejected(String businessCode) implements SaveOutcome {}
record SaveFailed(String technicalCode, Throwable cause)
        implements SaveOutcome {}
~~~

Đây là **fragment Java 17**, không phải file chạy độc lập. Nó làm rõ rằng lưu thành công khác bị từ chối vì nghiệp vụ và khác thao tác lưu bị lỗi.

Khi API công khai, caller xử lý kết quả:
- `Saved` → xác nhận thành công.
- `Rejected` → hiển thị lý do nghiệp vụ.
- `SaveFailed` → error code, retry policy, ghi nhận sự cố.

Nếu typed result là chuẩn của module, đừng trộn `null` trả về trong một API và `SaveFailed` ở API tương đương mà không nói rõ. Một enum error code nên **ổn định**, không chỉ là chuỗi `Throwable.getMessage()` vốn có thể thay đổi theo driver, locale và phiên bản code.

### 15.1. Truyền exception hay Result?

| Chọn cách nào? | Khi nào hợp lý? | Trách nhiệm |
| --- | --- | --- |
| `T` + `throws IOException` | Lỗi thực thi ngoại lệ, caller cần biết | Giữ cause/stack; không nuốt |
| `Optional<T>` + exception | Chỉ có/missing là nhánh dữ liệu bình thường | Chỉ empty khi đã xác nhận vắng mặt |
| `Result<T, E>` | Có nhiều trạng thái dự kiến và caller cần phân loại | Trả đủ trạng thái, không đánh tráo mã |
| `Fallback<T>` | Policy cho phép dùng giá trị thay thế | Thể hiện nguồn, độ tươi, giới hạn |
| `null` có contract cụ thể | API legacy/framework yêu cầu null có ý nghĩa đơn nhất | Tài liệu và test rõ; lỗi khác đi kênh riêng |
| `boolean`/primitive mặc định | Kết quả thực sự nhị phân/giá trị mặc định có ý nghĩa | Không dùng nó để che lỗi khác cùng miền |

Không nhất thiết xây dựng framework Result quá lớn cho một phương thức đơn giản. Nguyên tắc cần giữ là **một kết cục quan trọng phải được nhận diện tại tầng ra quyết định**.

## 16. Backward compatibility: sửa API legacy mà không làm hỏng caller

Nếu một API đã công khai `User getUser(id)` và lâu nay có thể trả null, đổi ngay thành `Result<User>` có thể làm vỡ code sử dụng. Cách chuyển đổi an toàn hơn:
1. Xác minh ý nghĩa `null` hiện tại qua test/hợp đồng chính thức, không suy từ vài caller.
2. Tạo API mới tên rõ, ví dụ `findUser(id)` trả `Optional<User>` và truyền exception, hoặc `lookupUser(id)` trả typed result.
3. Viết adapter chuyển giữa mới và cũ khi cần, nhưng không làm mất thông tin lỗi quan trọng ở một API được quảng bá là an toàn.
4. Đánh dấu/ghi tài liệu deprecation nếu migration có lộ trình.
5. Cập nhật caller ở ranh giới HTTP, batch, async và UI để xử lý đủ nhánh.
6. Thêm metric theo dõi việc còn gọi API cũ trước khi loại bỏ.

Cẩn trọng: một adapter cũ buộc phải trả null có thể không diễn đạt được các nhánh mới. Nếu không thể thay signature, có thể cần truyền exception ra ngoài với kiểu phù hợp thay vì âm thầm trả null. Phương án thực tế phụ thuộc compatibility và quy tắc xử lý lỗi hiện có.

### 16.1. Annotation nullability chưa đủ

Annotation như `@Nullable`, `@NonNull` hay thông tin trong JSpecify/IDE có thể giúp static analysis phát hiện khả năng nhận null, nhưng:
- Không tự giải thích **vì sao** null xuất hiện.
- Không cam kết caller phân biệt null hợp lệ với lỗi đã bị nuốt.
- Không phải mọi annotation đều được runtime tự động kiểm tra.
- Không thay thế tài liệu về exception/result.

Nếu hợp đồng là “null = không tìm thấy”, còn “backend unavailable = exception”, ghi rõ cả hai trong Javadoc và test. Đừng chỉ thêm annotation vào một API đã mơ hồ rồi tuyên bố vấn đề được giải quyết.

## 17. Thu exception đầy đủ và giữ nguyên nhân khi báo lỗi

Giả sử code:

~~~java
try {
    return repository.load(id);
} catch (IOException e) {
    return fallback;
}
~~~

Đây là fragment. Nếu `fallback` là dữ liệu cũ được phép dùng, bạn vẫn cần:
- ghi metric lỗi của nguồn chính;
- phân biệt result degraded với result chính;
- giữ exception/cause trong log nội bộ khi phục vụ điều tra;
- đánh dấu đã dùng fallback trên trace khi có thể;
- xác định lỗi nào được phép phục hồi bằng fallback.

Không nên log đầy đủ stack trace ở **mọi tầng** rồi rethrow gây trùng lặp. Chọn ranh giới sở hữu reporting, truyền cause qua wrapper/result để không mất thông tin; với kênh bên ngoài, chỉ xuất message an toàn.

Mẫu bọc hợp lý:

~~~java
try {
    return repository.load(id);
} catch (IOException e) {
    throw new ServiceUnavailableException("User store unavailable", e);
}
~~~

Đây là fragment; `ServiceUnavailableException` có thể là một custom RuntimeException/checked exception và phải được định nghĩa trong project thật. Constructor mang `cause` cho phép tầng API chuyển sang mã lỗi phù hợp, log có stack trace gốc và correlation ID.

### 17.1. Đừng tạo lỗi thứ cấp thay nguyên nhân gốc

Nếu catch lỗi rồi trả `null`, caller có thể ném `NullPointerException` ở vị trí xa hơn. Log cuối chỉ thấy NPE mà không thấy `IOException`. Đây là lý do nên giữ cause ngay khi lỗi xảy ra, không chờ tới lúc một thao tác khác fail.

Nếu chuyển lỗi thành `Result.Failed`, có thể giữ `Throwable` **nội bộ** hoặc một error object có thông tin tracing phù hợp. Không làm message text trở thành hợp đồng parser của caller.

## 18. Kết quả mặc định và tính đúng đắn của retry

Một lỗi I/O được đổi thành kết quả mặc định sẽ ngăn caller kích hoạt retry theo chính sách. Ví dụ:
- API tìm kiếm trả `List.of()` → caller nghĩ thực sự không có đơn cần xử lý.
- Job scheduler nhận `true` → đánh dấu công việc DONE, không retry.
- ETL nhận `0` → ghi báo cáo “0 bản ghi”, bỏ sót cả batch.
- Permission service trả `false` → tất cả bị từ chối, nhưng không báo sự cố hạ tầng.
- Inventory service trả `0` → hệ thống đóng bán dù hàng thực tế có thể còn.

Ngược lại, nếu callback retry **sau một timeout không rõ trạng thái**, việc chạy lại có thể nhân đôi side effect. Vì thế cũng không nên tự động biến mọi lỗi thành `Retryable`.

Một chính sách đầy đủ thường cần các loại:
- `RETRYABLE_TRANSIENT` nếu có bằng chứng thao tác an toàn để retry.
- `PERMANENT_VALIDATION` nếu input cần sửa.
- `UNKNOWN_OUTCOME` nếu request có thể đã hoàn tất ở remote.
- `CANCELLED` nếu có yêu cầu hủy hợp lệ.
- `SUCCESS`/`NOT_FOUND` đúng hợp đồng.

Với thao tác có side effect, cần **operation ID/idempotency key được server thực thi đúng** và quy trình tra cứu/đối soát trạng thái. Một HTTP timeout không chứng minh server chưa commit; trả `null` hoặc `false` có thể che sự không chắc chắn đó.

## 19. Transaction và trạng thái một phần

Ví dụ quy trình:
1. Ghi đơn hàng vào database.
2. Gửi lệnh thanh toán tới remote.
3. Ghi event audit.

Nếu lỗi xảy ra ở bước 2 hoặc 3, việc catch rồi trả `Order.default()` có thể nói sai rằng đơn hàng chưa được tạo, dù DB đã commit. Kể cả khi ném exception đúng, side effect đã có **không tự rollback**.

Nên thiết kế ranh giới:
- Trong một JDBC transaction chưa commit, rollback khi lỗi phù hợp và biết trạng thái connection.
- Với file publish, staging/temp + atomic move khi hỗ trợ, và cleanup file tạm thuộc quyền sở hữu.
- Với HTTP/payment/email, dùng idempotency, outbox/saga/compensation hoặc reconciliation theo tính chất hệ thống.
- Nếu outcome chưa xác định, trả `UNKNOWN`/`PENDING` thay vì giá trị mặc định ngụ ý chắc chắn.

Đừng giấu exception vì sợ caller thấy “failed” và retry sai. Cách đúng là **truyền một trạng thái mô tả chính xác sự không chắc chắn** và thiết kế retry an toàn.

## 20. Batch và aggregate: rỗng không có nghĩa mọi task thành công

Một `List<Result>` rỗng có thể nghĩa là:
- Danh sách input rỗng.
- Mọi task hoàn thành nhưng không có dữ liệu.
- Bộ tổng hợp lỗi nên đã bỏ qua kết quả.
- Một exception làm vòng lặp dừng trước khi thêm phần tử.

Nếu code:

~~~java
List<Item> items = new ArrayList<>();
for (String id : ids) {
    try {
        items.add(loadItem(id));
    } catch (IOException ignored) {
    }
}
return items;
~~~

Đây là fragment giả định `Item`, `ids` và `loadItem` đã được khai báo/import. Caller nhận list có thể thiếu phần tử mà không biết những ID nào lỗi. Trong nghiệp vụ báo cáo/đối soát, đây là dữ liệu không đầy đủ nhưng được trình bày như kết quả cuối.

Các cách rõ ràng:
- Fail fast và truyền exception nếu yêu cầu toàn bộ batch phải thành công.
- Trả `BatchResult(successes, failures)` có danh sách ID lỗi và nguyên nhân/mã lỗi.
- Trả kết quả từng item `Found/Missing/Failed` theo thứ tự input.
- Nếu bỏ qua lỗi từng phần là chủ đích, ghi rõ `partial=true` và thống kê số task thất bại.

Trong xử lý nhiều `Future` hoặc `CompletableFuture.allOf`, không chỉ đợi completion rồi trả `List.of()` khi một future fail. Lỗi của task cần được quan sát/tổng hợp theo hợp đồng. `isDone()` bao gồm cả hoàn thành lỗi hoặc hủy; nó không phải cờ thành công nghiệp vụ.

## 21. Thiết kế chỉ số giám sát cho failure và fallback

Nếu mọi exception bị chuyển thành kết quả “bình thường”, monitoring dựa trên số HTTP 5xx, exception counters hoặc exceptional completion của Future sẽ bỏ sót nhiều sự cố.

Các chỉ số nên phân biệt:

| Chỉ số/trạng thái | Ý nghĩa |
| --- | --- |
| `primary_success` | Nguồn chính trả kết quả hợp lệ |
| `not_found` | Truy vấn hoàn thành, không có dữ liệu |
| `technical_failure` | Lỗi ở nguồn chính, chưa phục hồi |
| `fallback_used` | Nguồn chính thất bại, chính sách dùng fallback |
| `fallback_failed` | Fallback cũng không thể tạo kết quả |
| `unknown_outcome` | Không thể khẳng định kết quả cuối (timeout sau side effect) |
| `cancelled` | Công việc bị hủy theo hợp đồng |
| `partial_result` | Batch chỉ có một phần kết quả, còn lỗi chưa xử lý/được báo |

Không dùng ID request duy nhất làm label cardinality cao của metric; lưu ở log/tracing phù hợp. Không log dữ liệu cá nhân, token, stack trace ra response public. Với fallback, metric success cuối và metric primary failure **đều có thể tăng** tùy mục đích: một thước đo chất lượng nguồn chính, một thước đo khả năng phục hồi trải nghiệm người dùng.

### 21.1. Log và catch không nhất thiết là cùng tầng

Không phải mọi `catch` đều phải log ERROR. Nếu tầng thấp bắt để bọc exception và ném tiếp, có thể để tầng ranh giới log một lần. Nếu một nhánh fallback phục hồi được, có thể ghi metric/trace degraded thay vì in cùng stack trace nhiều nơi.

Điều bắt buộc là **tín hiệu thất bại hoặc recovery status không biến mất**, không phải số lượng dòng log.

## 22. Kiểm thử: tiêm lỗi và chứng minh các trạng thái không bị trộn

Một test chỉ chạy đường thành công là chưa đủ. Một ma trận nên gồm:

| Dữ liệu/điểm tiêm lỗi | Kết quả đúng kỳ vọng |
| --- | --- |
| Bản ghi có tồn tại | `Found(value)` |
| Truy vấn thành công không thấy | `Missing`/`Optional.empty()` |
| Database ném `IOException` | `Failed(STORAGE_UNAVAILABLE)` hoặc exception |
| Lỗi cấu hình/parsing | Báo invalid config; không tự default nếu giá trị đã được cung cấp |
| Nguồn chính lỗi nhưng cache hợp lệ | `Fallback(value, provenance)` nếu policy cho phép |
| Nguồn chính lỗi và không có cache | `Failed`, không có `Found("")` |
| Fallback quá hạn/khác tenant | Không trả fallback như dữ liệu hợp lệ |
| Task async ném exception | Future/stage giữ failure hoặc typed result rõ |
| Task bắt lỗi rồi trả `null` | Test phát hiện vi phạm contract |
| Caller timeout trước worker kết thúc | `UNKNOWN`/timeout đúng chính sách, không tự NotFound |
| Batch có một phần failure | Các failure được giữ trong báo cáo, không mất ID |
| API có side effect rồi lỗi | Không báo chắc chắn “chưa có gì xảy ra” nếu đã commit |

### 22.1. Ví dụ JUnit 5 cho result có kiểu

Đoạn sau là **fragment** cho project đã có JUnit Jupiter và class `ExplicitFailureResultDemo` ở ví dụ runnable. Cần static imports từ `org.junit.jupiter.api.Assertions`:

~~~java
var found = ExplicitFailureResultDemo.lookup("A");
assertInstanceOf(ExplicitFailureResultDemo.Found.class, found);

var missing = ExplicitFailureResultDemo.lookup("B");
assertInstanceOf(ExplicitFailureResultDemo.Missing.class, missing);

var failed = ExplicitFailureResultDemo.lookup("DB_DOWN");
var error = assertInstanceOf(ExplicitFailureResultDemo.Failed.class, failed);
assertEquals(ExplicitFailureResultDemo.FailureCode.STORAGE_UNAVAILABLE,
        error.code());
assertInstanceOf(IOException.class, error.cause());
~~~

Test này chứng minh ba nhánh không bị gộp. Với API dùng `Optional` cộng `throws IOException`, test phải xác nhận empty chỉ khi truy vấn hoàn tất bình thường và lỗi storage truyền exception.

### 22.2. Kiểm tra contract với mock/fake

Nếu repository thật khó tiêm lỗi, dùng fake dependency có thể:
- Trả bản ghi.
- Trả không có bản ghi.
- Ném đúng exception hạ tầng.
- Ném exception lập trình bất ngờ.
- Đợi quá deadline.
- Thực hiện side effect rồi ném.

Hãy kiểm tra **output + cause + state sau lỗi + trạng thái metric/job**, không chỉ assert “phương thức không crash”. Với code có tính đồng thời, dùng latch/future timeout để test có điều phối; không dựa vào `Thread.sleep` đoán scheduling.

### 22.3. Property/invariant test hữu ích

Một vài bất biến có thể kiểm tra:
- Nếu repository ném exception mà không có fallback được phép, API **không** trả `Found`/`NotFound`.
- Nếu `Fallback` được trả, metadata phải nói rõ nguồn và đáp ứng giới hạn tuổi dữ liệu.
- Nếu `Missing` được trả, không có lỗi đọc nguồn trong lượt thao tác tương ứng.
- Nếu caller nhận `SUCCESS`, mọi bước bắt buộc của contract đã hoàn thành hoặc có cơ chế cam kết bền vững.
- Nếu kết quả `UNKNOWN`, code không tự retry non-idempotent command với operation ID mới.
- Không dùng cùng một sentinel cho hai kết cục cần xử lý khác nhau.

Đây là các tính chất có thể áp vào contract test trong CI; không nên hardcode stack trace/số dòng của code source vào unit test chức năng.

## 23. Những anti-pattern cần nhận diện trong code review

### 23.1. `catch (Exception e) { return null; }`

Vấn đề: mất loại lỗi và cause, trộn nhiều kết cục. Khắc phục: bắt chính xác loại có thể xử lý; nếu không phục hồi, truyền exception hoặc typed result.

### 23.2. `catch (RuntimeException e) { return 0; }`

Vấn đề: lỗi lập trình cũng biến thành số 0. Với dữ liệu số quan trọng, sai số có thể lan vào tính tiền/báo cáo. Khắc phục: kiểm tra input và lỗi đúng ranh giới; không dùng 0 làm “lỗi” nếu 0 hợp lệ.

### 23.3. `exceptionally(error -> List.of())`

Vấn đề: CompletableFuture hoàn thành bình thường bằng list rỗng khi nguồn lỗi. Các observer sau đó có thể ghi nhận success. Khắc phục: giữ exceptional completion hoặc chuyển sang `Failure` có mã.

### 23.4. `Optional.empty()` từ mọi lỗi I/O

Vấn đề: mất khác biệt absence/unavailable, nguy cơ negative cache sai. Khắc phục: chỉ empty khi đã xác nhận vắng mặt.

### 23.5. `return false` từ thao tác lưu khi remote timeout

Vấn đề: `false` có thể ngụ ý đã thất bại chắc chắn, trong khi server đã commit. Khắc phục: mô hình `UNKNOWN`/operation ID và đối soát.

### 23.6. `return defaultConfig` sau lỗi parse

Vấn đề: cấu hình sai âm thầm được chấp nhận. Khắc phục: dùng default chỉ cho absence nếu contract định nghĩa; dữ liệu cấu hình invalid phải báo rõ.

### 23.7. Log `e.getMessage()` rồi return null

Vấn đề: log có thể không có stack/cause; caller vẫn thấy kết quả giả. Khắc phục: truyền trạng thái lỗi rõ ràng và log throwable ở điểm phù hợp khi cần.

### 23.8. `return null` trong `finally`

Fragment sai:

~~~java
String compute() {
    try {
        throw new IllegalStateException("calculation failed");
    } finally {
        return null;
    }
}
~~~

Đây là **mã Java hoàn chỉnh ở mức phương thức**, cần đặt trong một class để biên dịch. Một `return` trong `finally` có thể **che exception hoặc kết quả** từ khối `try`. Tránh đặt `return` trong `finally` để chỉ cung cấp default; dùng `finally` cho cleanup an toàn, không thay điều khiển kết quả chính một cách bất ngờ.

### 23.9. Dùng kết quả mặc định mà không công bố chế độ degraded

Vấn đề: caller không biết giá trị đến từ cache hay nguồn chính. Khắc phục: trả provenance/freshness hoặc một trạng thái rõ ràng phù hợp API.

### 23.10. Nuốt `InterruptedException` rồi trả success/default

Vấn đề: mất tín hiệu shutdown/cancellation, task có thể tiếp tục sai trạng thái. Khắc phục: propagate hoặc restore interrupt flag và kết thúc theo contract; không coi đây là lỗi nghiệp vụ không đáng kể.

## 24. Hướng dẫn quyết định nhanh

~~~text
Đang định catch exception rồi trả một giá trị mặc định?
|
+-- Giá trị đó có phải kết quả hợp lệ của thao tác?
|      +-- Có -> có nguy cơ trộn success/absence/failure
|      +-- Không -> cần contract nói rõ sentinel và bảo đảm caller kiểm tra
|
+-- Exception có thể được phục hồi thực sự?
|      +-- Không -> giữ exception/cause hoặc trả Failure rõ ràng
|      +-- Có -> thực hiện recovery có giới hạn và xác minh hậu điều kiện
|
+-- Fallback có được nghiệp vụ cho phép?
|      +-- Có -> trả value + provenance/status phù hợp
|      +-- Không -> không tạo success giả
|
+-- Có side effect hoặc remote timeout?
|      +-- Có -> có thể cần Partial/Pending/Unknown + operation ID
|      +-- Không -> kết quả thất bại theo API
|
+-- Ai cần biết kết quả cuối?
       +-- Caller / coordinator / metric / job store
       +-- bảo đảm thông tin thất bại không bị cắt ở catch
~~~

Đây là cây quyết định định hướng. Nếu một tình huống thật sự chỉ có hai trạng thái và default được contract định nghĩa đầy đủ, không cần ép vào một hierarchy phức tạp. Nhưng một khi caller cần phân biệt **không có dữ liệu** với **không thể đọc dữ liệu**, một sentinel duy nhất không còn đủ.

## 25. Checklist trước khi đưa API vào production

- [ ] `null`, giá trị rỗng, `0`, `false` và default object có **ý nghĩa được ghi rõ**.
- [ ] Absence được phân biệt với lỗi hạ tầng/timeout/cancellation.
- [ ] Không dùng `Optional.empty()` để che IOException/SQLException nếu empty nghĩa là NotFound.
- [ ] `catch` chỉ bắt những exception đúng chính sách; không nuốt bug nhờ catch quá rộng.
- [ ] Nếu không thể phục hồi, exception được truyền hoặc chuyển thành `Failure` có mã và cause.
- [ ] Fallback được phép theo nghiệp vụ, có nguồn, độ tươi và giới hạn rõ.
- [ ] Khi cache kết quả NotFound, chỉ cache một absence đã được xác nhận.
- [ ] `CompletableFuture.exceptionally`/`handle` không tự tạo “success giả” bằng giá trị mặc định không có nhãn.
- [ ] Future được quan sát đầy đủ, không bỏ qua exception chỉ vì task đã hoàn tất.
- [ ] Timeout/interrupt/cancel không bị chuyển thành kết quả thành công nếu chưa đủ bằng chứng.
- [ ] API HTTP phân biệt 404 thật với 503/500 và Pending khi cần.
- [ ] Có operation ID/idempotency khi side effect remote có thể hoàn tất dù caller timeout.
- [ ] Không xuất stack trace, bí mật hoặc cause thô ra response public.
- [ ] Monitoring theo dõi primary failure, fallback used, technical failure và unknown outcome.
- [ ] Test tiêm lỗi vào dependency chứng minh code không gộp các trạng thái cần phân biệt.
- [ ] Đã cân nhắc backward compatibility và tài liệu khi thay đổi kiểu trả về API legacy.

## 26. Bài tập thực hành

Một service nhận yêu cầu lấy giá sản phẩm, trả `BigDecimal`. Cách hiện tại:

~~~java
BigDecimal getPrice(String sku) {
    try {
        return priceRepository.get(sku);
    } catch (Exception ignored) {
        return BigDecimal.ZERO;
    }
}
~~~

Đây là **fragment** với `BigDecimal` và `priceRepository` giả định.

Hãy trả lời và triển khai:
1. Nếu sản phẩm có giá **0 đồng** hợp lệ, caller phân biệt thế nào với lỗi database?
2. Nếu `sku` không tồn tại, nên trả `Optional<BigDecimal>`, ném một `NotFoundException` hay result `Missing`? Chọn một contract và giải thích.
3. Nếu giá được dùng để thanh toán, có được lấy giá cache cũ khi nguồn lỗi không? Phải kiểm tra những invariant nào?
4. Nếu API HTTP trả 200 với giá 0 sau `SQLException`, các hệ thống phía dưới có thể mắc sai lầm nào?
5. Viết một sealed result type `PriceFound`, `PriceMissing`, `PriceUnavailable`; giữ error code ổn định và cause nội bộ.
6. Tạo fake repository cho ba tình huống found/missing/exception. Thêm test rằng exception **không được chuyển thành giá 0 hợp lệ**.
7. Giả sử lookup giá được chạy trong `CompletableFuture`: thay `exceptionally(e -> BigDecimal.ZERO)` bằng một stage trả result có kiểu hoặc giữ exceptional completion. Kiểm tra metric không đếm lỗi là thành công.
8. Nếu giá đã được dùng tạo đơn rồi lỗi gửi thông báo, giải thích vì sao không được trả giá 0/ngụ ý không có đơn hàng và cần trạng thái nào cho side effect đã xảy ra.

**Kết luận:** Một giá trị mặc định không tự mang ý nghĩa “thất bại”. Khi contract không nêu rõ, việc catch exception rồi trả `null`, `false`, `0`, `Optional.empty()` hoặc collection rỗng có thể biến lỗi thật thành dữ liệu có vẻ hợp lệ. Hãy **tách absence, failure, fallback và unknown**, giữ nguyên nhân lỗi, và kiểm thử đường thất bại để caller nhận đúng sự thật về kết quả của thao tác.