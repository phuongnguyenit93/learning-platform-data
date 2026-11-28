# Quyền truy cập của canonical constructor so với record

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — tìm hiểu các cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này sử dụng quy tắc ngôn ngữ đã được chuẩn hóa từ Java 16, không dựa vào tính năng preview hoặc cách làm đã lỗi thời.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao **canonical constructor** (constructor chuẩn) phải có mức truy cập phù hợp với mức truy cập của `record`.
- Phân biệt mức truy cập của canonical constructor **được trình biên dịch sinh ngầm** và canonical constructor **tự khai báo**.
- Viết đúng modifier cho constructor chuẩn dạng đầy đủ hoặc dạng **compact**.
- Nhận diện trường hợp constructor `public` nhưng kiểu record vẫn không được phép truy cập từ bên ngoài.
- Thiết kế API record có kiểm tra dữ liệu đầu vào mà vẫn duy trì đúng quy tắc truy cập của Java.

## 1. Quy tắc cốt lõi

Record là một kiểu dữ liệu có các component được nêu trong phần khai báo. Với:

```java
public record UserId(String value) {}
```

Java cung cấp một **canonical constructor** tương ứng với component `String value`, cho phép tạo đối tượng bằng:

```java
UserId id = new UserId("U-001");
```

Về **quyền truy cập**, Java áp dụng hai quy tắc:

1. **Không khai báo canonical constructor:** trình biên dịch tạo một constructor chuẩn có **mức truy cập giống mức truy cập của record**.
2. **Có khai báo canonical constructor:** mức truy cập của constructor chuẩn phải **ít nhất rộng bằng mức truy cập của record**. Có thể rộng hơn nếu ngữ cảnh khai báo cho phép.

Nói cách khác, khi một record được công khai, canonical constructor của nó cũng phải công khai. Điều này giữ cho cơ chế khởi tạo dựa trên các component của record luôn khả dụng đối với mã có quyền truy cập vào kiểu record.

**Phân biệt hai loại quyền truy cập:** muốn thực hiện `new SomeRecord(...)`, mã gọi phải truy cập được **cả kiểu `SomeRecord` lẫn constructor phù hợp**. Một constructor `public` không tự động biến kiểu record thành `public`.

## 2. Record `public`: canonical constructor phải `public`

Đặt khai báo sau trong tệp `UserId.java`:

```java
public record UserId(String value) {}
```

Không có constructor tường minh, Java sinh canonical constructor có mức truy cập `public`, về ý nghĩa tương đương:

```java
// Phiên bản thay thế để minh họa: không khai báo đồng thời
// với phiên bản không có constructor phía trên.
public record UserId(String value) {
    public UserId(String value) {
        this.value = value;
    }
}
```

Do đó mã ở package khác có thể gọi `new UserId("U-001")` khi kiểu được xuất hiện hợp lệ trên đường biên API (ví dụ, package được export nếu dùng named module).

Nếu tự viết constructor chuẩn, phải khai báo `public`:

```java
import java.util.Objects;

public record UserId(String value) {
    public UserId {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be empty");
        }
    }
}
```

`public UserId { ... }` là **compact canonical constructor**. Nó có tham số ngầm `value` được suy ra từ header, và trình biên dịch tự gán component field khi thân constructor kết thúc bình thường.

Điều quan trọng ở đây là **từ khóa `public` trước tên constructor**, vì quyền truy cập của bản compact cũng tuân theo quy tắc giống bản canonical đầy đủ.

### Ví dụ sai: thu hẹp quyền truy cập

```java
// SAI: constructor chuẩn có mức package-private,
// trong khi record được khai báo public.
public record UserId(String value) {
    UserId {
        if (value == null) {
            throw new IllegalArgumentException("null value");
        }
    }
}
```

Java sẽ báo lỗi biên dịch vì constructor chuẩn tự khai báo có quyền truy cập hẹp hơn record. Việc bỏ modifier ở đây tạo **package-private constructor**, không có nghĩa là trình biên dịch sẽ tự thêm `public`.

Với dạng đầy đủ, lỗi tương tự:

```java
// SAI: private canonical constructor cho public record.
public record UserId(String value) {
    private UserId(String value) {
        this.value = value;
    }
}
```

Cách sửa cả hai trường hợp: đổi modifier constructor chuẩn thành `public`.

## 3. Record package-private có những lựa chọn nào?

Record cấp cao nhất (top-level) có thể không khai báo `public`. Khi đó, bản thân record là **package-private**:

```java
// File: InternalTag.java
record InternalTag(String code) {}
```

Canonical constructor được sinh ngầm cũng có mức truy cập **package-private**. Mã trong cùng package có thể tạo đối tượng:

```java
InternalTag tag = new InternalTag("INTERNAL");
```

Có thể khai báo constructor chuẩn tường minh với mức truy cập package-private:

```java
record InternalTag(String code) {
    InternalTag {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
    }
}
```

Hoặc khai báo **rộng hơn**, bằng `public`:

```java
record InternalTag(String code) {
    public InternalTag {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
    }
}
```

Cả hai cách trên đều hợp lệ; mỗi đoạn là một **phiên bản thay thế** của `InternalTag`.

Tuy nhiên, dù constructor của phiên bản thứ hai là `public`, mã nằm ngoài package **không thể tham chiếu trực tiếp đến kiểu `InternalTag`**, vì chính record vẫn package-private. Đây là lý do cần kiểm tra quyền truy cập của **kiểu** và **constructor** một cách riêng biệt.

Mặt khác, không được khai báo canonical constructor `private` trong một record top-level package-private: `private` hẹp hơn mức truy cập package-private của kiểu.

## 4. Bảng quy tắc: constructor sinh ngầm và constructor tự khai báo

Bảng dưới đây xét các khai báo record hợp lệ trong phạm vi top-level hoặc record thành viên (member record) của một lớp:

| Mức truy cập record | Nơi khai báo | Canonical constructor sinh ngầm | Quyền tối thiểu của canonical constructor tường minh |
| --- | --- | --- | --- |
| `public` | Top-level hoặc member | `public` | `public` |
| Package-private (không ghi modifier) | Top-level hoặc member | Package-private | Package-private |
| `protected` | Member của kiểu bao ngoài phù hợp | `protected` | `protected` |
| `private` | Member của kiểu bao ngoài phù hợp | `private` | `private` |

**Lưu ý:**

- Record top-level không được khai báo `protected` hoặc `private`. Hai modifier này có thể áp dụng cho **member record** trong ngữ cảnh hợp lệ.
- Quy tắc “ít nhất rộng bằng record” áp dụng cho cả constructor chuẩn dạng đầy đủ và dạng compact.
- Mức truy cập sinh ngầm **bằng** record; mức truy cập của constructor khai báo tường minh **có thể rộng hơn** record. Bảng mô tả **mức tối thiểu**, không buộc các modifier phải luôn giống hệt nhau.
- Các modifier truy cập không liên quan đến thứ tự hay kiểu của component; đó là những quy tắc khác của canonical constructor.

## 5. Record lồng trong lớp: phải xét cả lớp bao ngoài

Record khai báo là thành viên của một lớp là một **nested record**, và theo quy tắc ngôn ngữ nó là member class **ngầm định `static`**. Vì vậy, nó không cần một instance của lớp bao ngoài để khởi tạo.

Ví dụ trong `Registry.java`:

```java
public class Registry {

    // Kiểu record chỉ dùng nội bộ Registry.
    private record Entry(String key, int revision) {}

    // Kiểu record được công khai qua Registry.
    public record Snapshot(String key, int revision) {}
}
```

Hai canonical constructor được sinh tự động:

- `Registry.Entry` có canonical constructor **private**, tương ứng với record `private`.
- `Registry.Snapshot` có canonical constructor **public**, tương ứng với record `public`.

Trong thân `Registry`, mã có thể tạo cả hai record:

```java
public class Registry {
    private record Entry(String key, int revision) {}
    public record Snapshot(String key, int revision) {}

    public Snapshot snapshot() {
        Entry entry = new Entry("A-1", 3);
        return new Snapshot(entry.key(), entry.revision());
    }
}
```

Bên ngoài, có thể tạo `Registry.Snapshot` (khi `Registry` và package chứa nó có thể truy cập):

```java
Registry.Snapshot snapshot = new Registry.Snapshot("A-1", 3);
```

Ngược lại, `Registry.Entry` là kiểu `private` nên mã bên ngoài `Registry` không được tham chiếu trực tiếp đến nó.

### Constructor khai báo tường minh trong nested record

```java
public class Registry {

    private record Entry(String key) {
        private Entry {
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException("key is required");
            }
        }
    }

    public record Snapshot(String key) {
        public Snapshot {
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException("key is required");
            }
        }
    }
}
```

Ví dụ này dùng đúng mức truy cập tối thiểu của từng canonical constructor: `private` cho `Entry` và `public` cho `Snapshot`.

Một constructor tường minh của nested record có thể rộng hơn quyền của record; tuy vậy, **constructor công khai không mở rộng quyền truy cập của kiểu record**.

## 6. Kiểm tra cả quyền truy cập kiểu lẫn quyền truy cập constructor

Hình dung thư viện có hai package:

```text
src/
  com/example/internal/InternalCode.java
  com/example/api/PublicCode.java
  com/example/client/Client.java
```

Record package-private trong package nội bộ:

```java
// InternalCode.java
package com.example.internal;

record InternalCode(String value) {
    public InternalCode {}
}
```

Canonical constructor ở đây là `public` và **hợp lệ**, nhưng kiểu `InternalCode` vẫn package-private. Vì vậy, mã trong `com.example.client` không thể viết:

```java
// SAI: không thể truy cập kiểu InternalCode từ package khác.
com.example.internal.InternalCode code =
        new com.example.internal.InternalCode("X");
```

Muốn cho bên ngoài dùng trực tiếp, thư viện cần đưa kiểu vào API với mức truy cập phù hợp:

```java
// PublicCode.java
package com.example.api;

public record PublicCode(String value) {
    public PublicCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
    }
}
```

Từ package khác trong môi trường phù hợp:

```java
import com.example.api.PublicCode;

PublicCode code = new PublicCode("X");
```

**Khi ứng dụng dùng Java Platform Module System (JPMS):** ngoài modifier `public`, package của API phải được module tương ứng `exports` tới mã sử dụng; các điều kiện về `requires`/khả năng đọc module vẫn áp dụng. Đây là **lớp kiểm soát truy cập cấp module**, không thay đổi quy tắc quyền truy cập của canonical constructor.

Do đó khi một lời gọi `new` báo lỗi quyền truy cập, hãy xác định đang vướng **quyền truy cập kiểu**, **constructor**, hay **ranh giới module**.

## 7. Không thể ẩn canonical constructor của một `public record`

Với class thông thường, bạn có thể viết constructor `private` để buộc bên ngoài phải qua factory method. Nhưng với **public record**, canonical constructor phải là `public`. Ví dụ này không hợp lệ:

```java
// SAI: không được ẩn canonical constructor của public record.
public record Port(int number) {
    private Port(int number) {
        this.number = number;
    }

    public static Port of(int number) {
        return new Port(number);
    }
}
```

Nếu cần factory có tên dễ đọc, vẫn có thể cung cấp, nhưng canonical constructor phải công khai và **tự bảo vệ bất biến dữ liệu**:

```java
public record Port(int number) {

    public Port {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException(
                    "TCP/UDP port must be between 1 and 65535"
            );
        }
    }

    public static Port of(int number) {
        return new Port(number);
    }
}
```

Cả hai cách khởi tạo đều hợp lệ và đều đi qua kiểm tra:

```java
Port a = Port.of(8080);
Port b = new Port(8080);

// Port.of(0);    // IllegalArgumentException
// new Port(0);   // IllegalArgumentException
```

Khi chọn record cho API công khai, hãy thiết kế dựa trên đặc tính **có canonical constructor công khai**. Nếu yêu cầu thiết kế thực sự là cấm mã bên ngoài gọi constructor rồi buộc đối tượng được tạo qua factory, một **class thông thường** thường phù hợp hơn.

## 8. Constructor nạp chồng có quyền truy cập riêng

Quy tắc không được hẹp hơn record áp dụng cho **canonical constructor**. Một **constructor nạp chồng (non-canonical)** có thể dùng modifier khác, chẳng hạn `private`, miễn là constructor đó ủy quyền đến constructor khác của cùng record theo quy tắc Java.

```java
public record UserId(String value) {

    public UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
    }

    // Constructor phụ, không phải canonical constructor.
    private UserId() {
        this("GUEST");
    }

    public static UserId guest() {
        return new UserId();
    }
}
```

Lời gọi từ bên ngoài:

```java
UserId normal = new UserId("U-001"); // Được: canonical public
UserId guest  = UserId.guest();      // Được: factory public

// new UserId(); // SAI từ bên ngoài: overload không tham số là private
```

Hai constructor có mục đích và quy tắc khác nhau:

| Constructor | Chữ ký | Mức truy cập | Lý do |
| --- | --- | --- | --- |
| Canonical | `UserId(String value)` | `public` | Record `public` yêu cầu constructor chuẩn ít nhất `public`. |
| Nạp chồng | `UserId()` | `private` | Overload có modifier riêng và phải ủy quyền qua `this(...)`. |

Đừng dùng quyền `private` của constructor nạp chồng để suy ra rằng canonical constructor có thể `private`.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng cần ghi nhớ |
| --- | --- |
| “Không ghi modifier trong compact constructor của `public record` thì Java tự thêm `public`.” | Sai. Đó là constructor tường minh package-private và vi phạm quy tắc truy cập của canonical constructor. |
| “Constructor sinh ngầm luôn `public`.” | Sai. Nó có **cùng mức truy cập với record**. |
| “Constructor của record phải có mức truy cập giống hệt record.” | Chưa đủ chính xác. Constructor **sinh ngầm** có cùng mức; constructor **tường minh** được phép rộng hơn. |
| “Constructor `public` thì mọi package đều dùng được.” | Sai. Bản thân kiểu record phải truy cập được; với JPMS còn phải đáp ứng ranh giới module. |
| “Canonical constructor có thể `private` như class thường để chỉ dùng factory.” | Không hợp lệ với `public record`. |
| “Mọi constructor trong public record phải `public`.” | Sai. Ràng buộc này áp dụng cho **canonical constructor**; overload có thể `private`. |
| “Nested record cần instance của outer class để gọi constructor.” | Sai. Member record ngầm định `static`. |

## 10. Luyện tập và đáp án

### Bài 1: Constructor nào hợp lệ?

Xét record:

```java
public record Temperature(double celsius) {}
```

Có thể thay phần thân rỗng bằng phiên bản nào?

**A**

```java
public record Temperature(double celsius) {
    Temperature {
        if (Double.isNaN(celsius)) {
            throw new IllegalArgumentException("NaN");
        }
    }
}
```

**B**

```java
public record Temperature(double celsius) {
    public Temperature {
        if (Double.isNaN(celsius)) {
            throw new IllegalArgumentException("NaN");
        }
    }
}
```

**Đáp án:** Chỉ **B** hợp lệ. A thiếu `public` nên canonical constructor tường minh có mức truy cập hẹp hơn record.

### Bài 2: Vì sao không gọi được từ package khác?

```java
// package com.example.internal;
record SessionKey(String text) {
    public SessionKey {}
}
```

Một lớp ở `com.example.client` cố gọi `new SessionKey("abc")` và gặp lỗi truy cập.

**Đáp án:** `SessionKey` là kiểu package-private. Dù canonical constructor `public`, bên ngoài package vẫn không nhìn thấy kiểu. Muốn công khai type phải khai báo `public record SessionKey` và đặt trong tệp `SessionKey.java`, đồng thời đảm bảo các điều kiện module nếu dùng JPMS.

### Bài 3: Constructor `private` nào có thể giữ lại?

```java
public record AccountId(String value) {
    public AccountId {
        if (value == null) {
            throw new IllegalArgumentException("value");
        }
    }

    private AccountId() {
        this("ANONYMOUS");
    }
}
```

**Đáp án:** Cả hai constructor đều hợp lệ. `public AccountId { ... }` là canonical constructor; `private AccountId()` là constructor nạp chồng, ủy quyền bằng `this("ANONYMOUS")`. Mã bên ngoài vẫn gọi được `new AccountId("A-1")` nhưng không gọi được `new AccountId()`.

### Bài 4: Nên chọn record hay class?

Một thư viện muốn một kiểu dữ liệu công khai mà mã bên ngoài **không bao giờ được phép gọi bất kỳ constructor nào**, chỉ được tạo đối tượng thông qua một phương thức factory có thể chọn trả về instance cache sẵn.

**Gợi ý đáp án:** Một class thông thường có constructor `private` thường hợp hơn. Với `public record`, canonical constructor bắt buộc là `public` nên mã bên ngoài có thể trực tiếp gọi constructor đó.

## Ghi nhớ

- Canonical constructor **sinh ngầm** có cùng mức truy cập với record.
- Canonical constructor **tường minh**, kể cả compact constructor, phải có mức truy cập **ít nhất rộng bằng** record.
- Truy cập một constructor không đảm bảo truy cập được kiểu chứa nó; phải xét thêm lớp bao ngoài, package và ranh giới module.
- Quy tắc quyền truy cập của canonical constructor **khác** constructor nạp chồng.
- Với `public record`, đặt các kiểm tra tính hợp lệ ngay trong canonical constructor để mọi đường khởi tạo đều được kiểm soát.

## Tài liệu tham khảo

- [Java Language Specification — `8.10.4, Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4).
- [Java Language Specification — `6.6, Access Control](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.6).
- [JEP 395 — Records (hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
