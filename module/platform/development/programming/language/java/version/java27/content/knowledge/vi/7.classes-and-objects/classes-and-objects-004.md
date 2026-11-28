# Đóng gói trạng thái và kiểm soát phạm vi truy cập

Trong lập trình hướng đối tượng với **Java 27**, một đối tượng thường có **trạng thái** (state) và các **hành vi** (behavior) tác động lên trạng thái đó. Chẳng hạn, một ví điện tử có số dư, nhưng không phải mã nguồn nào cũng được phép tự ý sửa số dư. Các thao tác nạp hoặc trừ tiền phải kiểm tra điều kiện hợp lệ trước khi thay đổi dữ liệu.

**Đóng gói (encapsulation)** là thiết kế để đối tượng tự quản lý trạng thái và những quy tắc bảo đảm trạng thái luôn hợp lệ. **Kiểm soát phạm vi truy cập (access control)** là cơ chế của ngôn ngữ giúp xác định mã nào được phép nhìn thấy hoặc gọi một lớp, constructor, field hay method. Hai khái niệm liên quan chặt chẽ, nhưng không hoàn toàn đồng nhất: chỉ gắn `private` cho field vẫn chưa đủ nếu một phương thức công khai làm lộ đối tượng có thể sửa đổi bên trong.

Trong module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**, bài này sử dụng cú pháp, API và quy tắc đang áp dụng ở Java SE 27; ví dụ tập trung vào class, record, collection bất biến và module Java hiện hành.

## 1. Trạng thái, bất biến và ranh giới của đối tượng

**Trạng thái** là dữ liệu mà đối tượng nắm giữ tại một thời điểm, thường được lưu bằng instance fields. **Bất biến nghiệp vụ (invariant)** là điều kiện phải luôn đúng trong mọi trạng thái hợp lệ của đối tượng.

Ví dụ, với một ví lưu số tiền bằng đơn vị nhỏ nhất (cent):

- Số dư không âm.
- Số tiền nạp hoặc rút phải lớn hơn 0.
- Rút tiền không được khiến số dư âm.
- Phép cộng phải được kiểm tra để tránh tràn kiểu `long`.

Nếu nhiều thành phần bên ngoài có thể trực tiếp sửa field `balanceCents`, lớp `Wallet` không thể bảo đảm các điều kiện này. Để duy trì bất biến, mọi thay đổi trạng thái cần đi qua một điểm kiểm soát rõ ràng.

Sơ đồ tư duy:

```text
Mã gọi bên ngoài
      |
      v
  Public API: credit(), debit(), balanceCents()
      |
      v
  Kiểm tra đầu vào + bất biến nghiệp vụ
      |
      v
  Private state: balanceCents
```

Đóng gói đem lại lợi ích thực tế: giảm sự phụ thuộc vào cấu trúc lưu trữ nội bộ, giúp thay đổi cách triển khai mà ít ảnh hưởng người dùng của lớp, tập trung xử lý lỗi, và cho phép kiểm thử hành vi thông qua API có chủ đích.

## 2. Bốn mức truy cập trong Java

Java cung cấp ba từ khóa access modifier và một mức mặc định không viết từ khóa:

| Mức truy cập | Khai báo | Phạm vi truy cập điển hình |
| --- | --- | --- |
| **Private** | `private` | Bên trong lớp khai báo và các trường hợp truy cập của lớp bao/nested class theo quy tắc Java |
| **Package access** (package-private) | Không ghi access modifier | Các kiểu mã trong cùng package theo quy tắc truy cập của Java |
| **Protected** | `protected` | Cùng package; ngoài package thì mã của subclass có thể truy cập theo những điều kiện chặt chẽ hơn |
| **Public** | `public` | Mã bên ngoài nếu bản thân kiểu cũng truy cập được; giữa các named modules còn phải xét `requires` và `exports` |

### 2.1. `private`: bảo vệ chi tiết triển khai

Fields dùng để duy trì invariant thường nên là `private`. Các method kiểm tra đầu vào, tính toán nội bộ và helper không cần xuất hiện trong hợp đồng bên ngoài cũng nên có mức truy cập nhỏ nhất đủ dùng.

```java
public final class Counter {
    private int count;

    public void increment() {
        count = Math.addExact(count, 1);
    }

    public int value() {
        return count;
    }
}
```

Mã bên ngoài không thể viết `counter.count = -100;` vì field không thể truy cập trực tiếp. Nó chỉ có thể gọi phương thức mà `Counter` công khai.

`private` không có nghĩa chỉ từng instance được truy cập field của chính nó. Code trong cùng class có thể truy cập field private của **instance khác thuộc cùng class**. Trong Java, các nested class và kiểu bao quanh cũng có các quyền truy cập private được ngôn ngữ quy định; không nên suy rằng nested class luôn bị ngăn như một lớp độc lập ở package khác.

### 2.2. Package-private: API nội bộ của package

Nếu bỏ access modifier khỏi một field, method hoặc constructor thì thành viên đó có **package access**. Đây là lựa chọn phù hợp cho helper hoặc những thành phần chỉ nên được dùng bởi các lớp trong cùng package.

```java
package example.billing;

final class PriceRules {
    static void requireNonNegative(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("Negative price");
        }
    }
}
```

`PriceRules` là top-level class package-private. Một class ở package khác không thể import và sử dụng nó trực tiếp, kể cả khi các method bên trong được khai báo `public`. **Khả năng truy cập của một thành viên phụ thuộc cả khả năng truy cập của kiểu chứa thành viên đó.**

Tại top level, class/interface/record chỉ có thể khai báo `public` hoặc không khai báo access modifier (package-private). Không thể khai báo top-level class là `private` hoặc `protected`; các mức này được dùng cho thành viên, constructor và một số nested type thích hợp.

### 2.3. `protected`: thiết kế cho kế thừa có kiểm soát

Một thành viên `protected` được truy cập từ cùng package. Trong subclass ở package khác, quyền truy cập còn phụ thuộc ngữ cảnh và kiểu của đối tượng nhận truy cập, chứ không phải mọi object của lớp cha đều có thể bị truy cập.

Ví dụ hai class thuộc hai package khác nhau:

```java
// File: api/Base.java
package api;

public class Base {
    protected int count;
}
```

```java
// File: client/Derived.java
package client;

public class Derived extends api.Base {
    void update(Derived other, api.Base base) {
        count++;       // Hợp lệ: thành viên kế thừa của this
        other.count++; // Hợp lệ: đối tượng có kiểu Derived
        // base.count++; // Lỗi biên dịch ở package khác
    }
}
```

`protected` mở rộng phần bề mặt mà subclass có thể dựa vào. Vì vậy, tránh để subclass sửa trực tiếp mutable fields nếu hành động đó có thể phá invariant. Khi thật sự cần extension point, cân nhắc `protected` method có hợp đồng rõ ràng, trong khi state vẫn `private`.

### 2.4. `public`: hợp đồng đối với mã gọi

Khai báo `public` chỉ nên dùng cho những type, constructor và method thực sự thuộc API cần cung cấp:

```java
public long balanceCents() {
    return balanceCents;
}
```

`public` không bắt buộc các field cũng phải public. Một lớp có thể hoàn toàn public trong khi toàn bộ fields vẫn private. Các API ổn định thường công khai **hành vi** hoặc **giá trị chỉ đọc** thay vì công khai chi tiết dữ liệu có thể sửa trực tiếp.

## 3. Ví dụ đầy đủ: Wallet tự bảo vệ số dư

Lớp sau giữ `balanceCents` ở phạm vi `private` và chỉ cho phép thay đổi qua hai thao tác nghiệp vụ. Mỗi thao tác xác thực dữ liệu trước khi cập nhật.

```java
public final class Wallet {
    private long balanceCents;

    public Wallet(long openingBalanceCents) {
        if (openingBalanceCents < 0) {
            throw new IllegalArgumentException("Negative opening balance");
        }
        this.balanceCents = openingBalanceCents;
    }

    public long balanceCents() {
        return balanceCents;
    }

    public void credit(long amountCents) {
        requirePositive(amountCents);
        balanceCents = Math.addExact(balanceCents, amountCents);
    }

    public void debit(long amountCents) {
        requirePositive(amountCents);
        if (amountCents > balanceCents) {
            throw new IllegalStateException("Insufficient balance");
        }
        balanceCents -= amountCents;
    }

    private static void requirePositive(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
    }
}
```

Ví dụ sử dụng:

```java
Wallet wallet = new Wallet(10_000);
wallet.credit(2_500);
wallet.debit(1_200);
System.out.println(wallet.balanceCents()); // 11300

// wallet.balanceCents = -1; // Lỗi biên dịch: field private
// wallet.debit(-50);        // IllegalArgumentException nếu thực thi
```

Điểm đáng chú ý:

1. **Constructor kiểm tra trạng thái ban đầu:** không thể tạo ví có số dư âm qua public constructor.
2. **Không có setter tùy ý:** mã gọi không thể ghi trực tiếp `balanceCents`.
3. **Method diễn đạt nghiệp vụ:** `credit` và `debit` nói rõ việc đang thực hiện, thay vì một method mơ hồ như `setBalance`.
4. **Kiểm soát lỗi số học:** `Math.addExact` ném `ArithmeticException` nếu phép cộng `long` bị tràn. Do việc gán chỉ diễn ra khi phép cộng thành công, số dư cũ được giữ khi phép cộng lỗi.
5. **Dấu hiệu giới hạn thiết kế:** lớp trên **chưa thread-safe** nếu nhiều luồng cập nhật cùng lúc. Phạm vi `private` không tự giải quyết truy cập đồng thời; phần sau sẽ giải thích.

Dùng `long` để lưu cent chỉ nhằm minh họa tránh sai số dấu phẩy động. Hệ thống tài chính thực tế còn phải quy định loại tiền, độ lớn cho phép, cách làm tròn, đối soát, giao dịch và tính nhất quán giữa các tài khoản.

## 4. Đóng gói hướng vào invariant, không phải việc tạo getter/setter tự động

Một cách thiết kế thiếu chặt chẽ là khai báo tất cả fields `private` rồi sinh getter và setter công khai cho mọi field:

```java
public class Order {
    private String status;

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

Ở đây, bất kỳ mã gọi nào cũng có thể đưa `status` thành một giá trị tùy ý. Việc đổi field từ public sang private đã giảm quyền truy cập trực tiếp, nhưng **vẫn chưa bảo vệ invariant** nếu setter không kiểm soát giá trị và các bước chuyển trạng thái.

Nếu đơn hàng chỉ được chuyển từ `NEW` sang `PAID` rồi `SHIPPED`, các method như `markPaid()` và `markShipped()` có thể phù hợp hơn. Mỗi method có trách nhiệm xác minh bước chuyển được phép và các điều kiện đi kèm.

Nguyên tắc lựa chọn:

- Không cung cấp setter khi không có nhu cầu nghiệp vụ thực sự.
- Nếu cần setter, xác thực đầu vào và toàn bộ invariant liên quan trước khi ghi.
- Xác thực ngay tại ranh giới của đối tượng, dù tầng giao diện hoặc controller đã xác thực trước đó.
- Ưu tiên API nói rõ **ý nghĩa thao tác**, thay vì chỉ lộ tên field lưu trữ.
- Hạn chế trả ra cấu trúc mutable dùng để duy trì invariant nội bộ.

## 5. `final` và bất biến: hai khái niệm cần phân biệt

`final` với field có nghĩa là biến đó chỉ được gán theo các quy tắc khởi tạo của Java, không thể gán lại sau khi khởi tạo. Điều này **không làm cho đối tượng mà field trỏ tới trở nên bất biến**.

```java
private final java.util.List<String> names = new java.util.ArrayList<>();

public void addName(String name) {
    names.add(name); // Hợp lệ: thay đổi nội dung List, không gán lại field
}
```

Tương tự, class `final` ngăn kế thừa nhưng không ngăn thay đổi các mutable fields của chính class. Một đối tượng có trạng thái bất biến thực sự cần được thiết kế sao cho không có đường nào có thể làm thay đổi những giá trị đã cam kết.

Đối tượng **immutable** thường có các đặc điểm:

- Các giá trị thành phần được khởi tạo và xác thực ngay khi tạo.
- Không cung cấp thao tác làm thay đổi trạng thái sau khi tạo.
- Không để mã gọi giữ hay nhận được tham chiếu có thể sửa các thành phần bên trong.
- Nếu chứa đối tượng mutable, thực hiện defensive copy phù hợp.

Một object immutable thường dễ chia sẻ giữa nhiều luồng hơn vì không có thay đổi trạng thái cần phối hợp. Dù vậy, tính immutable của object không tự động khiến mọi quy trình dùng nó đều thread-safe.

## 6. Nguy cơ lộ mutable state và cách sao chép phòng vệ

### 6.1. Getter trả về collection mutable

Ví dụ rò rỉ trạng thái:

```java
public final class TaskBoard {
    private final java.util.List<String> tasks = new java.util.ArrayList<>();

    public java.util.List<String> tasks() {
        return tasks; // Trả về chính List nội bộ: mã gọi có thể sửa
    }
}
```

Mã ngoài có thể chạy `board.tasks().clear()` và thay đổi dữ liệu mà không qua method kiểm tra của `TaskBoard`. Access modifier `private` của field đã bị vượt qua về mặt thiết kế vì tham chiếu đến object mutable được công khai.

Có thể trả về **bản chụp (snapshot) không sửa đổi được**:

```java
public java.util.List<String> tasks() {
    return java.util.List.copyOf(tasks);
}
```

Với `tasks` là `ArrayList` nội bộ có thể sửa, `List.copyOf` tạo ra list kết quả không cho thêm, xóa hay thay phần tử. Các thay đổi tiếp theo trên `tasks` không tự động làm bản snapshot đã trả thay đổi. Phương thức từ chối phần tử `null`; cần có chính sách về null trước khi dùng.

Phân biệt hai cách thường gặp:

| Cách trả về | Hành vi quan trọng |
| --- | --- |
| `Collections.unmodifiableList(tasks)` | Trả về **view** không cho mã gọi sửa qua view, nhưng nếu list gốc đổi thì dữ liệu quan sát qua view cũng đổi |
| `List.copyOf(tasks)` | Với list gốc mutable, trả về **snapshot** không sửa đổi được; thay đổi cấu trúc list gốc sau đó không làm snapshot đổi |

Hai phương pháp đều chỉ bảo vệ ở **mức cấu trúc collection**. Nếu phần tử bên trong là object mutable, mã gọi có thể vẫn thay đổi trạng thái của phần tử đó. Để bảo vệ đầy đủ, cần sử dụng phần tử immutable hoặc sao chép sâu có chủ đích.

### 6.2. Sao chép dữ liệu đầu vào

Đóng gói cũng bị phá vỡ nếu constructor giữ nguyên tham chiếu tới collection mà người gọi cung cấp:

```java
import java.util.List;
import java.util.Objects;

public final class CourseCatalog {
    private final List<String> topics;

    public CourseCatalog(List<String> topics) {
        this.topics = List.copyOf(Objects.requireNonNull(topics));
    }

    public List<String> topics() {
        return topics;
    }
}
```

Vì các phần tử là `String` bất biến và list lưu trữ không sửa được, caller không thể sửa danh sách nội bộ bằng cách thay đổi list đã truyền vào hoặc gọi method mutating trên list được trả về.

### 6.3. Array cần sao chép ở cả đầu vào lẫn đầu ra

Array luôn có thể thay đổi phần tử, nên chỉ dùng `final` cho field array không đủ:

```java
import java.util.Objects;

public final class DocumentDigest {
    private final byte[] bytes;

    public DocumentDigest(byte[] source) {
        this.bytes = Objects.requireNonNull(source).clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }
}
```

`clone()` ở đây tạo bản sao của mảng một chiều gồm primitive `byte`, đủ để ngăn người gọi sửa nội dung mảng nội bộ. Với mảng chứa các object mutable hoặc mảng lồng nhau, cần cân nhắc sao chép sâu hơn.

## 7. Record trong Java 27: đóng gói dữ liệu dạng giá trị

**Record** là tính năng Java ổn định, phù hợp khi một kiểu có mục tiêu chính là mang một tập giá trị cố định. Java sinh các field `private final` tương ứng với record components, accessor công khai, canonical constructor, `equals`, `hashCode` và `toString` theo quy tắc của record.

Ví dụ record kiểm tra dữ liệu và tạo bản sao phòng vệ:

```java
import java.util.List;
import java.util.Objects;

public record CoursePlan(String code, List<String> topics) {
    public CoursePlan {
        Objects.requireNonNull(code, "code");
        if (code.isBlank()) {
            throw new IllegalArgumentException("Code must not be blank");
        }
        topics = List.copyOf(Objects.requireNonNull(topics, "topics"));
    }
}
```

Trong compact canonical constructor, tham số `topics` được thay bằng bản sao không sửa đổi được trước khi Java tự gán nó vào field tương ứng. Vì `String` bất biến, phương thức truy cập `topics()` mặc định không làm lộ mutable elements.

**Record chỉ bảo đảm bất biến nông (shallow immutability).** Một record nhận trực tiếp array hoặc một object mutable vẫn có thể bị thay đổi gián tiếp thông qua tham chiếu đã chia sẻ. Nếu component là array, việc sao chép trong constructor mà không kiểm soát accessor cũng chưa đủ vì accessor mặc định trả về tham chiếu array; cần cân nhắc override accessor để trả bản sao.

Không bắt buộc thay mọi class bằng record. Với đối tượng cần thay đổi trạng thái có kiểm soát theo thời gian, như `Wallet`, class có private fields và methods nghiệp vụ thường rõ ràng hơn. Record phù hợp với dữ liệu dạng giá trị, thông điệp, cấu hình và snapshot đã được xác thực.

## 8. Giới hạn constructor và quyền tạo đối tượng

Access modifier cũng áp dụng cho constructor. Constructor `private` có thể ngăn mã bên ngoài tạo instance trực tiếp, từ đó buộc người gọi dùng static factory:

```java
public final class CustomerCode {
    private final String value;

    private CustomerCode(String value) {
        this.value = value;
    }

    public static CustomerCode of(String raw) {
        if (raw == null || !raw.matches("[A-Z0-9]{4,12}")) {
            throw new IllegalArgumentException("Invalid customer code");
        }
        return new CustomerCode(raw);
    }

    public String value() {
        return value;
    }
}
```

Mã gọi dùng `CustomerCode.of("AB12")` và không thể gọi `new CustomerCode("AB12")` từ bên ngoài class. Factory giúp tập trung quy tắc khởi tạo và có thể hỗ trợ cách đặt tên mang ý nghĩa nghiệp vụ.

Tuy nhiên, private constructor không tự ngăn mọi cơ chế tạo/khôi phục đối tượng của runtime hoặc framework. Không dùng nó như biện pháp bảo mật dữ liệu; mục tiêu chính là giới hạn API tạo đối tượng ở mã Java thông thường.

## 9. Đóng gói ở cấp package và module

Java có các ranh giới thiết kế từ nhỏ đến lớn:

1. **Class:** private fields và methods giúp giữ chi tiết triển khai bên trong type.
2. **Package:** package-private cho phép các class trong cùng package cộng tác mà không công khai toàn bộ helper cho package khác.
3. **Module (JPMS):** một named module có thể chỉ công khai các package được chỉ định bằng `exports`. Các package không export tiếp tục là chi tiết triển khai ở ranh giới module.

Ví dụ một thư viện có hai package:

```text
example.wallet.api       // API công khai
example.wallet.internal  // Triển khai nội bộ
```

File `module-info.java` của thư viện:

```java
module example.wallet {
    exports example.wallet.api;
}
```

Module sử dụng:

```java
module example.client {
    requires example.wallet;
}
```

Mã trong `example.client` có thể truy cập các **public types và public members phù hợp** thuộc `example.wallet.api`. Nó không thể trực tiếp dùng `example.wallet.internal` khi package đó không được export, dù class nội bộ có khai báo `public`.

Hai khai báo khác nhau cần phân biệt:

- `exports example.wallet.api;`: cho các module đọc được module này truy cập public API của package ở mức biên dịch và sử dụng thông thường.
- `opens example.wallet.model;`: cho phép deep reflection vào package ở runtime theo quy tắc module. `opens` không thay thế `exports` cho truy cập source code thông thường.

Có thể dùng dạng giới hạn `exports ... to ...` hoặc `opens ... to ...` khi chỉ muốn cấp quyền cho các named modules chỉ định. Không nên tự động mở toàn bộ package chỉ để một framework hoạt động; hãy công khai đúng phần mà framework cần theo tài liệu của nó.

JPMS bổ sung cơ chế đóng gói mạnh ở ranh giới module, nhưng access modifier và module declaration vẫn không phải hệ thống **xác thực và phân quyền người dùng**. Việc một method được gọi hợp lệ trong Java không đồng nghĩa người gọi có quyền xem hoặc sửa dữ liệu nghiệp vụ.

## 10. Kế thừa, subclass và bề mặt mở rộng

Một class không khai báo `final` có thể được kế thừa nếu các quy tắc khác cho phép. Một method được phép override có thể được subclass thay đổi hành vi. Điều này ảnh hưởng đến việc duy trì invariant:

- Mã của subclass có thể tận dụng `protected` members; nếu chúng cho phép thay đổi mutable state trực tiếp, invariant của lớp cha có thể bị phá.
- Khi thiết kế class để kế thừa, cần tài liệu hóa rõ các method được phép override và hợp đồng phải giữ.
- Nếu không có nhu cầu extension bằng subclass, `final class` thường giảm rủi ro do subclass thay đổi hành vi.
- Các cơ chế `sealed` hoặc `final` quyết định ai được kế thừa, không phải là access modifier tương đương `private` hoặc `protected`.

Trong Java, một method override không được giảm visibility của method mà nó override. Ví dụ, method `public` ở lớp cha phải vẫn là `public` trong bản override hợp lệ; không thể đổi nó thành `private`.

Một trường hợp cần chú ý là **không gọi method có thể bị override từ constructor** nếu subclass có thể làm thay đổi hành vi của method đó trước khi object khởi tạo hoàn tất. Việc xác thực và thiết lập invariant trong constructor nên dựa vào code mà class kiểm soát.

## 11. Đóng gói không tự bảo đảm thread safety

Field `private` ngăn mã ngoài truy cập trực tiếp theo quy tắc ngôn ngữ, nhưng không bảo đảm nhiều luồng sử dụng các public methods một cách an toàn.

Với ví `Wallet` ở mục 3, hai luồng có thể cùng đọc số dư cũ rồi ghi số dư mới; cập nhật của một luồng có thể bị ghi đè. Ngay cả việc cập nhật `long` bằng cách cộng một lượng cũng không tự trở thành thao tác nguyên tử.

Nếu `Wallet` cần được truy cập đồng thời, có thể chọn một chiến lược đồng bộ phù hợp:

- Sử dụng cùng một khóa `synchronized` cho cả method đọc và các method cập nhật số dư.
- Bảo đảm các bước **kiểm tra invariant và thay đổi state** nằm trong cùng vùng đồng bộ.
- Hoặc thiết kế dùng `Lock`, `AtomicLong` hay actor/message-passing phù hợp với cấu trúc ứng dụng và yêu cầu nhất quán.

Ví dụ, nếu dùng monitor của đối tượng, những method đọc/ghi liên quan có thể cùng mang `synchronized`:

```java
public synchronized long balanceCents() {
    return balanceCents;
}

public synchronized void credit(long amountCents) {
    requirePositive(amountCents);
    balanceCents = Math.addExact(balanceCents, amountCents);
}

public synchronized void debit(long amountCents) {
    requirePositive(amountCents);
    if (amountCents > balanceCents) {
        throw new IllegalStateException("Insufficient balance");
    }
    balanceCents -= amountCents;
}
```

Đây là cách thay thế ba method tương ứng trong class `Wallet`, không phải ba method độc lập có thể biên dịch ngoài class. Khi tất cả truy cập liên quan dùng cùng monitor, thao tác kiểm tra rồi ghi được bảo vệ khỏi các luồng khác dùng cùng cơ chế.

`volatile` giúp về **visibility** và thứ tự bộ nhớ đối với field tương ứng, nhưng không khiến chuỗi thao tác đọc–sửa–ghi như `count++` trở thành nguyên tử. Tương tự, `final` không biến collection mutable thành thread-safe.

## 12. Những sai lầm thiết kế thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `public long balance;` | Mọi mã gọi có thể ghi số dư trái quy tắc | `private` field, public method kiểm soát thay đổi |
| Tạo setter cho mọi field | Cho phép thao tác không gắn với invariant | Ưu tiên method diễn đạt hành vi nghiệp vụ |
| Getter trả `ArrayList` nội bộ | Mã ngoài có thể xóa/sửa state | Snapshot bằng `List.copyOf` khi phù hợp |
| Constructor giữ nguyên `List` được truyền vào | Caller vẫn có thể sửa state sau khi tạo | Defensive copy ngay khi nhận dữ liệu |
| `private final List` rồi cho rằng immutable | `final` không khóa nội dung List | Thiết kế bất biến ở cấp đối tượng và phần tử |
| Public mutable static field | Tạo trạng thái dùng chung khó kiểm soát | Private state, API rõ ràng, phối hợp đồng bộ nếu cần |
| Dùng `protected` cho mutable field | Subclass có thể bỏ qua kiểm tra của lớp cha | State `private`; extension qua method có hợp đồng |
| Public type trong package không export | Module khác không dùng trực tiếp được | Export đúng package API cần công khai |
| Dùng `opens` thay `exports` | Mở quyền reflection nhưng không cấp truy cập source-level thông thường | Dùng đúng khai báo theo mục đích |
| Cho rằng `private` bảo đảm thread safety | Race condition vẫn xảy ra qua public methods | Đồng bộ toàn bộ bước kiểm tra và cập nhật |
| Dùng access control làm phân quyền người dùng | Không giải quyết authentication/authorization | Kiểm tra quyền nghiệp vụ ở ranh giới dịch vụ phù hợp |

## 13. Kiểm tra đóng gói trong code review và kiểm thử

Khi review một class có mutable state, có thể đặt các câu hỏi sau:

1. **Invariant của đối tượng là gì?** Mỗi field có điều kiện hợp lệ cụ thể hay không?
2. **Có đường ghi nào bỏ qua xác thực không?** Bao gồm public/protected fields, setters, constructors, callback và mutable references đã bị lộ.
3. **Đầu vào có được sao chép khi cần không?** Đặc biệt với arrays, collections và object mutable.
4. **Đầu ra có làm lộ state không?** Getter trả reference sống, view của collection hay snapshot? Các phần tử bên trong có mutable không?
5. **Mức truy cập đã nhỏ nhất đủ dùng chưa?** Tránh xuất các helper và member không thuộc API ổn định.
6. **Package và module exports có hợp lý không?** Thư viện chỉ công khai những package được hỗ trợ chính thức.
7. **Lớp có được thiết kế cho subclass không?** Nếu có, protected API và các override points có bảo toàn invariant không?
8. **Trạng thái có được chia sẻ giữa nhiều luồng không?** Các bước kiểm tra và cập nhật có atomic theo nhu cầu nghiệp vụ không?
9. **Có kiểm tra các trường hợp lỗi không?** Giá trị âm, null, dữ liệu không hợp lệ, overflow, thao tác sai trạng thái và các tình huống tranh chấp đồng thời.

Để kiểm tra `Wallet`, nên có những trường hợp: không tạo được số dư đầu âm; không nạp/rút số tiền không dương; không rút vượt số dư; số dư sau chuỗi thao tác đúng; nạp gây tràn `long` phải ném lỗi mà không sửa số dư. Các trường hợp truy cập private field từ lớp khác được trình biên dịch kiểm tra, còn invariant runtime cần kiểm thử hành vi.

## 14. Kết luận

Đóng gói hiệu quả bắt đầu từ **invariant của đối tượng**. Access modifiers giúp kiểm soát mã Java nào nhìn thấy type/member, còn phương thức nghiệp vụ, kiểm tra đầu vào và defensive copy giúp trạng thái không bị sửa trái phép qua các API hợp lệ.

Trong Java 27, hãy ưu tiên `private` cho mutable fields, package-private cho helper nội bộ, `protected` khi có nhu cầu thiết kế kế thừa rõ ràng và `public` cho hợp đồng cần hỗ trợ. Kết hợp `final`, class bất biến hoặc record khi phù hợp, đồng thời nhớ rằng bất biến nông và thread safety là các vấn đề riêng. Với ứng dụng theo JPMS, `exports` và `opens` bổ sung ranh giới giữa các module.

Mục tiêu của encapsulation là khiến **mọi trạng thái có thể quan sát được đều được tạo ra qua những chuyển đổi hợp lệ**, đồng thời giữ đủ tự do thay đổi cách triển khai mà không phá vỡ hợp đồng với mã gọi.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — Chapter 6: Names, mục 6.6 Access Control](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-6.html#jls-6.6) — các mức truy cập, package-private và giới hạn `protected`.
- [Java Language Specification, Java SE 27 — Chapter 8: Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html) — class modifiers, fields, constructors, inheritance, nested classes và record.
- [Java Language Specification, Java SE 27 — Chapter 7: Packages and Modules](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html) — khai báo và khả năng truy cập package/module.
- [List (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html) — `List.copyOf`, unmodifiable collections và giới hạn shallow immutability.
- [Record (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html) — record components, constructor, accessors và shallow immutability.
- [Objects (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html) — `Objects.requireNonNull`.
- [Math (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html) — phép toán kiểm tra overflow bằng `Math.addExact`.
