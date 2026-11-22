# Dùng test nhỏ để cô lập pattern lỗi trong Java Pattern Matching

## 1. Mục tiêu: chuyển “pattern sai” thành một trường hợp có thể tái hiện

Khi gặp lỗi liên quan tới `instanceof` pattern, record pattern hoặc `switch` có pattern trong Java, kết quả nhìn thấy thường chỉ là “chọn sai nhánh”, “không vào case”, “ném NullPointerException” hoặc “compile không qua”. Đó mới là **triệu chứng**, chưa phải nguyên nhân.

Thay vì đọc cả một phương thức xử lý nghiệp vụ dài rồi đoán, hãy tạo **test nhỏ, xác định**, kiểm tra lần lượt các giai đoạn:

```text
Giá trị đầu vào
      |
      v
Biểu thức selector có đánh giá thành công không?
      |
      v
Đối tượng có đúng kiểu pattern không?
      |
      v
Record ngoài và các record con có khớp không?
      |
      v
Accessor đã trả component hợp lệ hay ném lỗi?
      |
      v
Điều kiện when/&& có đúng không?
      |
      v
Case nào được chọn? Thân case tạo kết quả gì?
```

Ý tưởng cốt lõi: **mỗi test chỉ cần trả lời một câu hỏi**, dùng dữ liệu nhỏ nhất có thể cho câu hỏi đó. Sau khi tìm được bước sai, giữ lại một **regression test** để lần sửa tiếp theo không làm lỗi quay lại.

Trong bài này, “cô lập” nghĩa là:

- Rút bài toán còn một hoặc vài record, một phương thức có pattern và vài input rõ ràng.
- So sánh **expected** (hành vi theo yêu cầu) với **actual** (hành vi chương trình thực tế).
- Tách kiểm tra **kiểu**, **hình dạng record**, **guard**, **null** và **hành vi của thân nhánh**.
- Chỉ thay đổi một giả thuyết mỗi lần, không đồng thời đổi tên kiểu, đảo nhánh và viết lại toàn bộ switch.

Ví dụ sử dụng **Java 21+** vì record patterns và pattern matching for switch là tính năng chính thức trong Java 21 (JEP 440, JEP 441). Với type pattern `instanceof` đơn giản, tính năng đã chính thức từ Java 16.

## 2. Một lỗi cụ thể: địa chỉ toàn khoảng trắng lại được chấp nhận

Hãy xét hai record:

```java
record Address(String city) {}
record Shipment(String shipmentId, Address destination) {}
```

Yêu cầu nghiệp vụ:

- Địa chỉ giao hàng có thành phố chứa ký tự có nghĩa thì trả nhãn dạng `ship:Da Nang`, sau khi bỏ khoảng trắng hai đầu.
- Nếu `destination` bằng `null`, hoặc `city` bằng `null`, hoặc `city` toàn khoảng trắng, trả `destination:missing`.
- Nếu selector bằng `null`, trả `input:missing`.
- Nếu selector không phải `Shipment`, trả `unsupported`.

Đây là phiên bản **cố ý có lỗi**:

```java
static String buggy(Object candidate) {
    return switch (candidate) {
        case null -> "input:missing";
        case Shipment(var shipmentId, Address(var destinationCity))
                when destinationCity != null ->
                "ship:" + destinationCity.strip();
        case Shipment(var shipmentId, var destination) ->
                "destination:missing";
        default -> "unsupported";
    };
}
```

Đoạn trên là phương thức minh họa; nó cần được đặt trong lớp có khai báo các record. Dòng gây vấn đề là **`when destinationCity != null`**. Điều kiện ấy cho phép chuỗi `"   "` đi qua vì chuỗi này **khác `null`**. Sau `strip()`, nhãn thành `"ship:"` dù nghiệp vụ yêu cầu `"destination:missing"`.

Không phải record pattern không khớp. Chính record pattern **khớp đúng**, nhưng guard quá rộng.

### Một minimal reproducer (MRE) thật sự chạy được

Lưu thành `TinyGuardRepro.java`:

```java
public class TinyGuardRepro {
    record Address(String city) {}
    record Shipment(Address destination) {}

    static String classify(Object candidate) {
        return switch (candidate) {
            case Shipment(Address(var city)) when city != null ->
                    "ship:" + city.strip();
            case Shipment(var destination) -> "destination:missing";
            case null -> "input:missing";
            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Shipment(new Address("   "))));
    }
}
```

Chạy:

```bash
javac --release 21 -encoding UTF-8 TinyGuardRepro.java
java TinyGuardRepro
```

Kết quả thực tế:

```text
ship:
```

Kỳ vọng theo nghiệp vụ: `destination:missing`.

Đây là một **reproducer của bug**, không phải lời khẳng định nó đã trả đúng. Nó đã loại bỏ framework, cơ sở dữ liệu, API, log và các phần không liên quan. Nếu bản tối giản vẫn tái hiện kết quả `ship:` thì ta có thể điều tra riêng phần pattern và guard.

## 3. Kỹ thuật chia lỗi thành ba test cực nhỏ

Để tránh đoán nguyên nhân, tách cùng đối tượng `new Shipment("S-2", new Address("   "))` thành các kiểm tra độc lập.

### Bước A — Kiểm tra kiểu ngoài

```java
static String typeOnly(Object candidate) {
    return candidate instanceof Shipment shipment
            ? "type:Shipment" : "type:other";
}
```

Với `Shipment` có thành phố toàn khoảng trắng, kết quả là `type:Shipment`. Nghĩa là đối tượng **đúng kiểu**, lỗi không nằm ở kiểm tra kiểu ngoài.

### Bước B — Kiểm tra record pattern, chưa áp dụng guard

```java
static String shapeOnly(Object candidate) {
    if (candidate instanceof Shipment(
            var shipmentId, Address(var destinationCity))) {
        return "shape:" + shipmentId + ":" + destinationCity;
    }
    return "shape:miss";
}
```

Với cùng input, kết quả là `shape:S-2:   ` (sau dấu hai chấm cuối có **ba dấu cách**). Mẫu record ngoài và mẫu `Address(...)` bên trong đều khớp; biến `destinationCity` chứa đúng chuỗi khoảng trắng.

### Bước C — Kiểm tra đúng điều kiện nghiệp vụ

```java
static String guardOnly(Object candidate) {
    if (candidate instanceof Shipment(
            var shipmentId, Address(var destinationCity))
            && destinationCity != null && !destinationCity.isBlank()) {
        return "guard:pass";
    }
    return "guard:fail";
}
```

Với chuỗi ba khoảng trắng, `isBlank()` là `true`, nên `!isBlank()` là `false` và kết quả là `guard:fail`. Đến đây có đủ bằng chứng rằng bug không nằm ở kiểu hay hình dạng record mà ở **guard thiếu điều kiện không rỗng/không trắng**.

Cách sửa trong switch:

```java
case Shipment(var shipmentId, Address(var destinationCity))
        when destinationCity != null && !destinationCity.isBlank() ->
        "ship:" + destinationCity.strip();
```

Dòng này là **một nhãn `case`** nằm bên trong switch, không phải câu lệnh độc lập. Giữ nguyên case `Shipment(var shipmentId, var destination)` phía sau để xử lý những địa chỉ không hợp lệ.

## 4. Ma trận dữ liệu nhỏ: mỗi hàng bảo vệ một giả thuyết

Với lỗi trên, không cần dữ liệu sản xuất khổng lồ. Chỉ cần vài đối tượng được xây dựng trong bộ nhớ.

| Input | Nhánh đúng kỳ vọng | Lý do |
| --- | --- | --- |
| `new Shipment("S-1", new Address(" Da Nang "))` | `ship:Da Nang` | Thành phố hợp lệ, bỏ khoảng trắng hai đầu |
| `new Shipment("S-2", new Address("   "))` | `destination:missing` | Chuỗi toàn khoảng trắng |
| `new Shipment("S-3", null)` | `destination:missing` | Thiếu cả record địa chỉ |
| `new Shipment("S-4", new Address(null))` | `destination:missing` | Record địa chỉ có, thành phần city null |
| `null` | `input:missing` | Selector null |
| `Integer.valueOf(17)` | `unsupported` | Kiểu ngoài không được hỗ trợ |

Mỗi input làm lộ **một khác biệt nghĩa**:

- `new Shipment("S-3", null)` kiểm tra mẫu record con `Address(...)` có khớp null hay không.
- `new Shipment("S-4", new Address(null))` kiểm tra mẫu `var destinationCity` có thể nhận giá trị null từ accessor của `Address`.
- `new Shipment("S-2", new Address("   "))` kiểm tra sự khác nhau giữa “không null” và “có nội dung hữu ích”.
- `null` kiểm tra chính sách null của **selector**, không phải null của thành phần.
- `17` kiểm tra `default` để bảo đảm sửa guard không vô tình đổi hành vi các kiểu khác.

**Mẹo:** chỉ thêm dữ liệu khác khi nó giúp phân biệt một nguyên nhân còn nghi ngờ. Nếu hai input làm lộ cùng một điều kiện, có thể để input thứ hai trong suite hồi quy nhưng không nhất thiết dùng cả hai trong minimal reproducer.

## 5. Ví dụ đầy đủ Java 21: cô lập, tái hiện và xác minh bản sửa

Lưu nguyên văn chương trình sau vào file **`IsolatePatternBugDemo.java`**. Bộ test nhỏ dùng `AssertionError` để thất bại rõ ràng khi expected khác actual, không cần JUnit hoặc framework khác.

Trong phần `reproduceBug`, ta **cố ý yêu cầu thấy khác biệt** để chứng minh mã lỗi còn tái hiện. Đây là hành vi kiểm tra một bug đã biết, không phải khẳng định `buggy(...)` đúng. Phần `fixed(...)` mới phải đáp ứng expected.

```java
public class IsolatePatternBugDemo {
    record Address(String city) {}
    record Shipment(String shipmentId, Address destination) {}

    record Fragile(String value) {
        public String value() {
            if (value == null) {
                throw new IllegalStateException("accessor failed");
            }
            return value;
        }
    }

    // Bug: city != null vẫn cho phép chuỗi toàn khoảng trắng.
    static String buggy(Object candidate) {
        return switch (candidate) {
            case null -> "input:missing";
            case Shipment(var shipmentId, Address(var destinationCity))
                    when destinationCity != null ->
                    "ship:" + destinationCity.strip();
            case Shipment(var shipmentId, var destination) ->
                    "destination:missing";
            default -> "unsupported";
        };
    }

    // Fix: thêm điều kiện !isBlank(), giữ các case còn lại.
    static String fixed(Object candidate) {
        return switch (candidate) {
            case null -> "input:missing";
            case Shipment(var shipmentId, Address(var destinationCity))
                    when destinationCity != null && !destinationCity.isBlank() ->
                    "ship:" + destinationCity.strip();
            case Shipment(var shipmentId, var destination) ->
                    "destination:missing";
            default -> "unsupported";
        };
    }

    // Bước 1: chỉ kiểm tra kiểu bên ngoài.
    static String typeOnly(Object candidate) {
        return candidate instanceof Shipment shipment
                ? "type:Shipment" : "type:other";
    }

    // Bước 2: phân rã record nhưng không kiểm tra nghiệp vụ.
    static String shapeOnly(Object candidate) {
        if (candidate instanceof Shipment(
                var shipmentId, Address(var destinationCity))) {
            return "shape:" + shipmentId + ":" + destinationCity;
        }
        return "shape:miss";
    }

    // Bước 3: kiểm tra guard riêng.
    static String guardOnly(Object candidate) {
        if (candidate instanceof Shipment(
                var shipmentId, Address(var destinationCity))
                && destinationCity != null && !destinationCity.isBlank()) {
            return "guard:pass";
        }
        return "guard:fail";
    }

    // Accessor cố ý ném ngoại lệ, giúp phân biệt lỗi matching.
    static String fragilePattern(Object candidate) {
        if (candidate instanceof Fragile(var value)) {
            return "fragile:" + value;
        }
        return "not-fragile";
    }

    // Không có case null: default không tự bắt selector null.
    static String noNullCase(Object candidate) {
        return switch (candidate) {
            case Shipment(var shipmentId, var destination) -> "shipment";
            default -> "other";
        };
    }

    static int passed;

    static void assertEqual(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " expected=" + expected
                    + " actual=" + actual);
        }
        passed++;
        System.out.println("PASS " + label + "=" + actual);
    }

    static void reproduceBug(String expected, String actual) {
        if (expected.equals(actual)) {
            throw new AssertionError("bug not reproduced");
        }
        System.out.println("REPRO blank expected=" + expected
                + " actual=" + actual);
    }

    public static void main(String[] args) {
        Shipment valid = new Shipment(
                "S-1", new Address(" Da Nang "));
        Shipment blank = new Shipment(
                "S-2", new Address("   "));
        Shipment missing = new Shipment("S-3", null);
        Shipment nullCity = new Shipment(
                "S-4", new Address(null));

        assertEqual("type-blank", "type:Shipment", typeOnly(blank));
        assertEqual("shape-blank", "shape:S-2:   ", shapeOnly(blank));
        assertEqual("guard-blank", "guard:fail", guardOnly(blank));
        reproduceBug("destination:missing", buggy(blank));

        assertEqual("fixed-valid", "ship:Da Nang", fixed(valid));
        assertEqual("fixed-blank", "destination:missing", fixed(blank));
        assertEqual("fixed-missing", "destination:missing", fixed(missing));
        assertEqual("fixed-null-city", "destination:missing", fixed(nullCity));
        assertEqual("fixed-null-selector", "input:missing", fixed(null));
        assertEqual("fixed-other", "unsupported", fixed(17));

        assertEqual("shape-null-destination", "shape:miss",
                shapeOnly(missing));
        assertEqual("shape-null-city", "shape:S-4:null",
                shapeOnly(nullCity));
        assertEqual("guard-valid", "guard:pass", guardOnly(valid));

        try {
            noNullCase(null);
            throw new AssertionError("NullPointerException expected");
        } catch (NullPointerException expected) {
            assertEqual("missing-case-null", "NullPointerException",
                    expected.getClass().getSimpleName());
        }

        try {
            fragilePattern(new Fragile(null));
            throw new AssertionError("MatchException expected");
        } catch (MatchException expected) {
            assertEqual("accessor-cause", "IllegalStateException",
                    expected.getCause().getClass().getSimpleName());
        }

        System.out.println("checks=" + passed);
    }
}
```

Chạy với JDK 21+:

```bash
javac --release 21 -encoding UTF-8 IsolatePatternBugDemo.java
java IsolatePatternBugDemo
```

**Đầu ra chính xác** (dòng `shape-blank` có ba dấu cách ngay trước khi xuống dòng):

```text
PASS type-blank=type:Shipment
PASS shape-blank=shape:S-2:   
PASS guard-blank=guard:fail
REPRO blank expected=destination:missing actual=ship:
PASS fixed-valid=ship:Da Nang
PASS fixed-blank=destination:missing
PASS fixed-missing=destination:missing
PASS fixed-null-city=destination:missing
PASS fixed-null-selector=input:missing
PASS fixed-other=unsupported
PASS shape-null-destination=shape:miss
PASS shape-null-city=shape:S-4:null
PASS guard-valid=guard:pass
PASS missing-case-null=NullPointerException
PASS accessor-cause=IllegalStateException
checks=14
```

**Ý nghĩa kết quả:**

- Ba dòng đầu là **ba lớp chẩn đoán**: kiểu khớp, record lồng khớp, điều kiện nghiệp vụ không đạt.
- Dòng `REPRO` chứng minh lỗi ở `buggy(blank)`: thực tế `ship:` khác expected `destination:missing`. Không được coi dòng đó là “test production pass”.
- Sáu dòng `fixed-*` khẳng định bản sửa xử lý địa chỉ hợp lệ, khoảng trắng, record con null, thành phần city null, selector null và kiểu lạ.
- Hai dòng `shape-null-*` chứng minh **record con null** khác **thành phần trong record con null**.
- Hai dòng về ngoại lệ tách **NullPointerException vì selector null không có case** khỏi **MatchException do accessor record ném lỗi** (nguyên nhân được lưu trong `getCause()`).
- `checks=14` là số assertion thành công ở các ca không cố ý sai; phép `reproduceBug` riêng không tăng biến đếm.

Ví dụ đã được chạy bằng cú pháp Java 21, kết quả được kiểm tra với các ca cụ thể. Toàn bộ chương trình chỉ dùng JDK, không cần framework hay file phụ trợ.

## 6. Đọc kết quả để khoanh vùng, không chỉ để “xanh test”

Một chuỗi điều tra đúng có thể diễn ra như sau:

| Phép thử | Kết quả | Kết luận hợp lệ |
| --- | --- | --- |
| `typeOnly(blank)` | `type:Shipment` | Đối tượng ngoài đúng kiểu `Shipment` |
| `shapeOnly(blank)` | `shape:S-2:   ` | `Address` con tồn tại; `city` chứa chuỗi ba dấu cách |
| `guardOnly(blank)` | `guard:fail` | Điều kiện hợp lệ nghiệp vụ phải từ chối giá trị này |
| `buggy(blank)` | `ship:` | Nhánh có guard hiện tại vẫn chấp nhận khoảng trắng |
| `fixed(blank)` | `destination:missing` | Bản sửa đáp ứng ca lỗi |
| `fixed(valid)` | `ship:Da Nang` | Bản sửa không phá hành vi với địa chỉ hợp lệ |

Lưu ý về thứ tự kết luận: từ `typeOnly` có kết quả đúng **không thể** suy ra record pattern lồng đúng; từ `shapeOnly` đúng **không thể** suy ra guard đúng; từ guard đúng **không thể** suy ra phần thân nhánh không có bug. Mỗi test chỉ khẳng định được đúng điều mà nó kiểm tra.

Đây là cách tránh một lỗi điều tra phổ biến: “đối tượng đúng class rồi, chắc chắn `switch` có lỗi”. Trên thực tế, lỗi có thể nằm ở `when`, dữ liệu thành phần, vị trí case, hoặc logic tạo kết quả.

## 7. Khi pattern không khớp: phân biệt kiểu, cấu trúc và guard

### 7.1. Sai kiểu ngoài

```java
Object candidate = Integer.valueOf(17);
boolean isShipment = candidate instanceof Shipment shipment;
```

`isShipment` là `false`. Record pattern `Shipment(...)` cũng không khớp. Không cần debug sâu hơn vào accessor của `Shipment` vì đối tượng này không phải `Shipment`.

### 7.2. Record con null

```java
Object candidate = new Shipment("S-3", null);

boolean deep = candidate instanceof Shipment(
        var shipmentId, Address(var destinationCity));
```

`deep` là `false`: selector là `Shipment`, nhưng mẫu record con `Address(...)` không khớp `null`. Test `shapeOnly(missing)` vì thế trả `shape:miss`. Điều này không có nghĩa selector bản thân là null, và cũng không tự động là exception.

### 7.3. Thành phần bên trong record con null

```java
Object candidate = new Shipment(
        "S-4", new Address(null));

boolean deep = candidate instanceof Shipment(
        var shipmentId, Address(var destinationCity));
```

Trong Java 21, mẫu `var destinationCity` có thể ràng buộc giá trị `null` của component tham chiếu, nên `deep` là `true`. Nếu guard chỉ kiểm tra sự tồn tại của `Address` mà không kiểm tra `city`, nghiệp vụ có thể lỗi sau đó.

### 7.4. Guard bị thiếu hoặc quá rộng

Một pattern có guard:

```java
case Shipment(var shipmentId, Address(var destinationCity))
        when destinationCity != null -> "ship:" + destinationCity.strip();
```

chấp nhận `""` và `"   "`. Nếu hợp đồng cần thành phố không blank, điều kiện hợp lệ phải bao gồm `!destinationCity.isBlank()`. Vì `&&` có short-circuit, kiểm tra `destinationCity != null` trước giúp không gọi `isBlank()` trên null.

### 7.5. Lỗi ở thân nhánh

Nếu cả pattern và guard đều phù hợp nhưng output vẫn sai, hãy tạo test độc lập cho thao tác trong thân nhánh, ví dụ `" Da Nang ".strip()` hoặc phép tính/formatter thực của ứng dụng. Đừng sửa `case` khi phép ghép chuỗi, định dạng tiền, chuyển đổi đơn vị hoặc service được gọi bên trong mới là nguồn lỗi.

## 8. Giữ nguyên dữ liệu và expected khi thu nhỏ reproducer

Một **minimal reproducible example** tốt có ba tính chất:

1. **Minimal:** ít loại dữ liệu, ít phương thức và ít nhánh nhất vẫn tái hiện lỗi.
2. **Reproducible:** chạy lại với cùng input cho cùng kết quả trong điều kiện kiểm thử đã xác định.
3. **Diagnostic:** kết quả cho phép bác bỏ hoặc xác nhận một giả thuyết cụ thể.

Rút gọn không có nghĩa thay đổi ngữ nghĩa:
- Nếu bug liên quan `null`, đừng thay null bằng `""` chỉ để ví dụ đẹp hơn.
- Nếu bug liên quan record con null, đừng bỏ record con ra khỏi mô hình khiến nhánh khớp khác.
- Nếu bug liên quan thứ tự các case, giữ tối thiểu hai case có quan hệ ưu tiên.
- Nếu bug liên quan accessor ném exception, đừng đổi record có accessor tùy chỉnh thành record chỉ dùng accessor mặc định.
- Nếu bug liên quan concurrency, mutable state hoặc I/O, hãy viết fixture có thể điều khiển được những yếu tố đó, thay vì xóa sạch nguyên nhân làm bug biến mất.
- Nếu bug phụ thuộc phiên bản, ghi rõ `javac --release` và runtime thực tế.

Để debug chương trình nhiều module, có thể bắt đầu từ một input thất bại trong integration test, tạo unit test cho phương thức nhỏ hơn, rồi rút tiếp xuống 1–2 record và một `switch`. Sau khi đã sửa, vẫn cần chạy integration test để bảo đảm bản sửa xử lý đúng dữ liệu và tương tác thật.

## 9. Khi có nhiều case: xem dominance, thứ tự và exhaustiveness

Trong `switch` có pattern, thứ tự của case không chỉ ảnh hưởng khả năng đọc mà còn liên quan đến tính hợp lệ của mã.

Ví dụ **cố ý không biên dịch**:

```java
return switch (candidate) {
    case Shipment(var id, var destination) -> "any shipment";
    case Shipment(var id, Address(var city)) -> "shipment with address";
    default -> "other";
};
```

Nếu mẫu `Shipment(var id, var destination)` ở đầu đã khớp mọi instance `Shipment` (kể cả component null), case `Shipment(var id, Address(var city))` phía sau bị **dominated**: không thể được chọn. Java 21 có thể báo lỗi dominance ở thời điểm biên dịch.

Để cô lập lỗi dominance, tạo test **biên dịch tối thiểu** chỉ gồm hai case có liên hệ che phủ. Không cần chạy cả hệ thống để tìm lỗi compiler. Cách sửa thường là đặt **mẫu cụ thể trước, mẫu rộng sau**:

```java
return switch (candidate) {
    case Shipment(var id, Address(var city)) -> "shipment with address";
    case Shipment(var id, var destination) -> "any shipment";
    default -> "other";
};
```

Đây là các **đoạn minh họa** sử dụng `candidate` và record `Shipment` đã khai báo. Chỉ đổi thứ tự nếu điều đó giữ đúng hợp đồng nghiệp vụ: pattern riêng có thể chỉ khớp một phần trường hợp của kiểu ngoài.

**Exhaustiveness** là lỗi khác: `switch expression` và `enhanced switch statement` có pattern phải bao phủ các khả năng thuộc kiểu selector theo quy tắc Java. Nếu thiếu nhánh với một kiểu mở như `Object`, cần một case tổng quát. Nhưng “đã exhaustive” vẫn **không đồng nghĩa xử lý selector null**. Khi có lỗi ở compile time, phân biệt thông báo `does not cover all possible input values` với `dominated case`, vì hai lỗi có nguyên nhân và cách sửa khác nhau.

## 10. Null selector và null component: test riêng để tìm đúng tầng

Xét ba đối tượng:

```java
Object a = null;
Object b = new Shipment("S-3", null);
Object c = new Shipment("S-4", new Address(null));
```

| Input | Đối tượng ngoài | Record con `Address` | Thành phần `city` | Diễn giải |
| --- | --- | --- | --- | --- |
| `a` | `null` | Không có | Không có | Selector null |
| `b` | `Shipment` | `null` | Không có | Record con null |
| `c` | `Shipment` | Có | `null` | Component của record con null |

Một `case null` trong `switch (candidate)` **chỉ** xử lý `a`. Nó không thay thế case cho `b` hay `c`. Với `b`, mẫu record lồng `Address(...)` không khớp; với `c`, mẫu `Address(var destinationCity)` có thể khớp nhưng biến thành phần nhận null.

Nếu một switch không có `case null`, `default` thông thường không xử lý selector null, và phép `switch` ném `NullPointerException`. Chương trình ở mục 5 kiểm tra tình huống đó bằng `noNullCase(null)` và xác minh đúng loại exception.

**Thêm test null ở đúng vị trí** giúp tránh chẩn đoán sai như “case null hỏng” trong khi dữ liệu thực ra là một `Shipment` không null có `Address` null.

## 11. Ngoại lệ do accessor: không được coi là “không khớp”

Một record có thể tự khai báo accessor với logic:

```java
record Fragile(String value) {
    public String value() {
        if (value == null) {
            throw new IllegalStateException("accessor failed");
        }
        return value;
    }
}
```

Lời gọi `candidate instanceof Fragile(var value)` buộc pattern matching gọi accessor để lấy component. Nếu accessor ném exception trong khi matching, Java 21 ném **`MatchException`**, chứa ngoại lệ gốc trong `getCause()`. Đó không phải trường hợp `instanceof` trả `false` như mismatch thông thường.

Bộ test đã cô lập riêng:

```java
try {
    fragilePattern(new Fragile(null));
    throw new AssertionError("MatchException expected");
} catch (MatchException expected) {
    assertEqual("accessor-cause", "IllegalStateException",
            expected.getCause().getClass().getSimpleName());
}
```

Nó cho thấy lỗi xuất hiện tại **đánh giá accessor khi matching**, không phải tại guard của `Shipment`. Muốn debug tiếp, kiểm tra thân accessor và dữ liệu record ở test nhỏ. Đừng dùng `default` để “bắt” lỗi accessor: matching đã kết thúc bất thường, không chạy nhánh dự phòng.

Ngược lại, nếu **guard `when`** ném ngoại lệ thì exception từ guard lan truyền theo quy tắc đánh giá biểu thức, không tự thành `MatchException` chỉ vì guard đứng trong `switch`. Test bắt ngoại lệ nên chỉ rõ nó xuất phát từ **selector expression**, **accessor khi matching**, **guard** hay **case body**.

## 12. Scope của pattern variable: cô lập bằng mã compile tối thiểu

Không phải lỗi nào cũng cần test runtime. Ví dụ **cố ý không biên dịch**:

```java
if (candidate instanceof Shipment shipment
        || shipment.destination() != null) {
    System.out.println("check");
}
```

Vế phải của `||` có thể được đánh giá khi `candidate` **không** phải `Shipment`; `shipment` chưa được ràng buộc ở đường này. Compiler từ chối việc dùng biến.

Nếu mục tiêu là “đúng kiểu Shipment và destination khác null”, viết:

```java
if (candidate instanceof Shipment shipment
        && shipment.destination() != null) {
    System.out.println("has destination");
}
```

Vế phải của `&&` chỉ chạy khi vế trái đúng, nên biến pattern có phạm vi hợp lệ. Để debug một lỗi scope, rút điều kiện về **một `instanceof` và một toán tử logic** rồi biên dịch. Không cần phát sinh record fixtures hoặc chạy test nếu lỗi là cú pháp/phạm vi ở compile time.

Với `case Shipment(var shipmentId, Address(var destinationCity)) when ...`, biến thành phần có thể sử dụng trong guard và nhánh được chọn. Nhưng không dùng nó ở case khác hay sau switch nếu compiler không bảo đảm scope. Thay tên biến không giải quyết lỗi phạm vi; cần thay cấu trúc điều khiển luồng.

## 13. Nếu test có side effects: đóng băng nguồn dữ liệu trước khi so khớp

Một phép thử nhỏ chỉ đáng tin khi chạy lại cho kết quả có thể dự đoán. Hãy chú ý nguồn dữ liệu có tác dụng phụ:

```java
// Minh họa rủi ro: hai lần gọi có thể trả hai đối tượng khác nhau.
if (queue.poll() instanceof Shipment) {
    Shipment shipment = (Shipment) queue.poll();
    process(shipment);
}
```

Đây là đoạn minh họa, giả định `queue` và `process` có trong ứng dụng. Nếu `poll()` lấy phần tử khỏi hàng đợi, lần kiểm tra và lần cast dùng **hai phần tử khác nhau**. Đổi sang:

```java
if (queue.poll() instanceof Shipment shipment) {
    process(shipment);
}
```

sẽ đánh giá `poll()` một lần, có thể là sửa lỗi đúng nhưng **không** chỉ là đổi cú pháp giữ behavior. Nếu bug phụ thuộc số lần đọc, test nhỏ cần dùng một queue với hai phần tử xác định và assert số phần tử còn lại.

Để kiểm thử riêng logic pattern mà không kéo theo side effects, có thể **đọc một lần** vào biến ổn định:

```java
Object candidate = queue.poll();
if (candidate instanceof Shipment shipment) {
    process(shipment);
}
```

Khi tách thành test đơn vị, hãy đưa `candidate` là một đối tượng record được tạo trực tiếp, không phụ thuộc mạng, database, random hoặc thời gian hệ thống. Những phụ thuộc ấy được kiểm thử ở tầng integration/contract riêng.

Đừng thêm `System.out.println` vào một accessor hoặc guard đang cần điều tra rồi kết luận hoàn toàn không ảnh hưởng: logging bản thân là side effect và trong hệ thống phức tạp có thể đổi lịch thực thi. Ưu tiên assertion, debugger và test data ổn định.

## 14. Dùng JUnit 5: tách failing test khỏi bản sửa

Trong dự án sử dụng JUnit 5, có thể đưa expected behavior vào unit test:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PatternDebugTest {
    @Test
    void blankDestinationMustBeRejected() {
        var blank = new IsolatePatternBugDemo.Shipment(
                "S-2", new IsolatePatternBugDemo.Address("   "));
        assertEquals("destination:missing",
                IsolatePatternBugDemo.fixed(blank));
    }

    @Test
    void nullDestinationIsDifferentFromNullSelector() {
        var missing = new IsolatePatternBugDemo.Shipment("S-3", null);
        assertAll(
                () -> assertEquals("destination:missing",
                        IsolatePatternBugDemo.fixed(missing)),
                () -> assertEquals("input:missing",
                        IsolatePatternBugDemo.fixed(null))
        );
    }

    @Test
    void nullWithoutCaseThrowsNpe() {
        assertThrows(NullPointerException.class,
                () -> IsolatePatternBugDemo.noNullCase(null));
    }

    @Test
    void accessorExceptionRetainsCause() {
        MatchException ex = assertThrows(MatchException.class,
                () -> IsolatePatternBugDemo.fragilePattern(
                        new IsolatePatternBugDemo.Fragile(null)));
        assertInstanceOf(IllegalStateException.class, ex.getCause());
    }
}
```

Đây là **lớp test minh họa, không phải chương trình chạy độc lập**: cần JUnit 5 và đặt test trong cùng package với `IsolatePatternBugDemo` hoặc điều chỉnh khả năng truy cập. Các method và nested record trong ví dụ chính có quyền truy cập package-private nên test cùng package có thể gọi.

Để **chứng minh lỗi gốc bằng một test đỏ**, thay `fixed(blank)` bằng `buggy(blank)` ở test đầu. Khi đó assertion `assertEquals("destination:missing", buggy(blank))` phải thất bại vì thực tế là `"ship:"`. Sau khi sửa code production, dùng lại chính test này với phương thức production đã được sửa; không giữ một assertion cố ý sai trong CI.

### Đừng viết test cho có

Mẫu kiểm thử yếu:

```java
@Test
void weakTest() {
    IsolatePatternBugDemo.fixed(new IsolatePatternBugDemo.Shipment(
            "S-2", new IsolatePatternBugDemo.Address("   ")));
}
```

Test trên chỉ gọi phương thức và không assert kết quả; rất có thể luôn xanh dù lỗi ban đầu vẫn còn. Một test debug hữu ích cần có:
- Input cụ thể làm lộ bug.
- Expected có cơ sở từ hợp đồng.
- Assertion hoặc exception expectation rõ ràng.
- Tên test nói được behavior.
- Ca đối chứng non-bug để hạn chế việc sửa một nhánh làm hỏng nhánh khác.

## 15. Red–green–refactor cho pattern lỗi

Quy trình ngắn, lặp lại được:

1. **Red:** viết test có expected theo nghiệp vụ, cho thấy bản hiện tại sai. Với bug của bài, `blankDestinationMustBeRejected` khi gọi `buggy` phải fail.
2. **Isolate:** thêm các test `typeOnly`, `shapeOnly`, `guardOnly` để chứng minh sai ở điều kiện `when`, không phải type checking hoặc accessor của `Shipment`.
3. **Fix:** đổi đúng guard `destinationCity != null` thành `destinationCity != null && !destinationCity.isBlank()`.
4. **Green:** chạy lại test đỏ; nó phải pass. Chạy các ca `valid`, `nullCity`, `missingAddress`, `nullSelector` và `unsupported` để bảo vệ hành vi khác.
5. **Refactor:** nếu muốn đổi cấu trúc switch hoặc trích phương thức, làm ở thay đổi tiếp theo và giữ các assertion xanh.
6. **Review:** giải thích vì sao điều kiện mới phù hợp hợp đồng; chỉ thêm case hoặc `default` nếu thực sự cần, không dùng chúng để che lỗi.

Có thể dùng kỹ thuật *mutation-oriented reasoning*: thử bỏ `!isBlank()` khỏi code đã sửa. Nếu test `fixed-blank` không thất bại, nghĩa là test chưa đủ nhạy. Tương tự, bỏ `case null` phải làm `fixed-null-selector` thất bại. Không cần luôn chạy công cụ mutation testing chuyên dụng để áp dụng cách suy nghĩ này.

## 16. Kiểm thử ở các tầng: unit, compiler và integration

| Loại lỗi | Công cụ/test nhỏ phù hợp | Dấu hiệu thành công |
| --- | --- | --- |
| Sai kiểu đầu vào | `instanceof` type pattern | Kết quả khớp/không khớp như dự kiến |
| Sai hình dạng record con | `instanceof` record pattern | Phân biệt record con null và component null |
| Guard thiếu điều kiện | Fixture ranh giới + assertion | Đầu vào trống/blank bị từ chối đúng |
| Case bị che phủ | Chương trình tối thiểu để `javac` biên dịch | Compiler báo dominance; thứ tự case được sửa |
| Switch thiếu case | Test compile với hierarchy phù hợp | Compiler nhận đủ tính exhaustive |
| Null selector | `assertThrows` hoặc `assertEquals` | Đúng chính sách NPE/`case null` |
| Accessor ném lỗi | Pattern trên record tùy chỉnh + catch `MatchException` | Kiểm tra cause đúng |
| Scope pattern variable | Đoạn biên dịch tối thiểu cho `&&`/`||` | Không còn lỗi “cannot find symbol” |
| Lỗi formatter trong case | Unit test cho hàm tạo chuỗi | Expected text/amount đúng |
| Tương tác hệ thống | Integration/contract test | Cùng side effect và dữ liệu liên kết |

Một test `javac` thất bại là bài test về **cú pháp/luật compile**, không có stdout runtime. Một test runtime về behavior cần chương trình **biên dịch thành công** rồi so expected/actual. Đừng trộn hai loại hoặc dùng lỗi compile của một ví dụ cố ý sai để khẳng định mọi test runtime đều fail.

## 17. Thực hành chẩn đoán theo triệu chứng

### Triệu chứng A: “Có dữ liệu nhưng không vào case record”

Hỏi lần lượt: selector có đúng kiểu ngoài không? Record con có null không? Mẫu lồng có đòi loại con quá cụ thể không? Có `when` bị sai không? Dùng `typeOnly`, `shapeOnly`, `guardOnly` với **cùng một fixture**.

### Triệu chứng B: “Vào case sai khi thêm mẫu rộng”

Kiểm tra thứ tự và dominance. Mẫu `Object` hoặc `Shipment(var id, var destination)` có thể bao phủ nhiều giá trị hơn người viết tưởng. Test hai input: một khớp mẫu hẹp và một chỉ khớp mẫu rộng.

### Triệu chứng C: “Null gây NPE dù có default”

Kiểm tra selector null hay một dereference trước switch. Nếu selector thật sự null, `default` thường không xử lý; cần `case null` hoặc chấp nhận NPE theo hợp đồng. Test riêng trường hợp selector null.

### Triệu chứng D: “Record pattern ném MatchException”

Kiểm tra accessor tùy chỉnh và `getCause()`. Đừng chuyển case khác một cách mù quáng; đó có thể là lỗi **trong lúc matching** thay vì mismatch.

### Triệu chứng E: “Thay `instanceof + cast` bằng pattern làm đổi kết quả”

Đếm số lần biểu thức được đánh giá, kiểm tra thứ tự nhánh và kiểu biến được truyền đến overload. Một nguồn có side effect như `queue.poll()` có thể làm phiên bản mới dùng đối tượng khác.

### Triệu chứng F: “Pattern variable không dùng được”

Kiểm tra flow scoping: `&&`, `||`, `!`, `return` sớm, scope của các case, tên biến trùng. Nếu compiler báo lỗi, đừng cố debug runtime trước khi có chương trình hợp lệ.

## 18. Bài tập và đáp án

**Bài 1 — Tìm tầng lỗi.** `typeOnly(blank)` trả `type:Shipment`, `shapeOnly(blank)` trả `shape:S-2:   `, nhưng `buggy(blank)` trả `ship:`. Nghi ngờ bước nào trước?

**Đáp án:** guard `destinationCity != null` không phân biệt chuỗi toàn khoảng trắng. Thêm `!destinationCity.isBlank()` và regression test cho `"   "`.

**Bài 2 — Minimal reproducer.** Để tái hiện lỗi trên, có cần database, HTTP controller và repository thật không?

**Đáp án:** không. Một `Shipment`, một `Address`, một switch và một input `"   "` đủ tái hiện bug. Các thành phần tích hợp vẫn cần test riêng nếu có nguy cơ gây lỗi khác.

**Bài 3 — Hai dạng null.** `new Shipment("S-3", null)` và `new Shipment("S-4", new Address(null))` có cùng cơ chế matching sâu không?

**Đáp án:** không. Trường hợp đầu làm mẫu `Address(...)` không khớp; trường hợp sau khớp record `Address`, còn `var destinationCity` nhận null. Với bản fix, cả hai đều dẫn tới nhánh `destination:missing`.

**Bài 4 — Một ca bug, một ca đối chứng.** Vì sao nên test thêm `" Da Nang "` sau khi sửa lỗi `"   "`?

**Đáp án:** để bảo đảm thay guard không vô tình từ chối dữ liệu hợp lệ có khoảng trắng thừa; expected phải là `ship:Da Nang`.

**Bài 5 — Lỗi compile.** Một case `Shipment(var id, var destination)` đứng trước `Shipment(var id, Address(var city))`. Điều gì có thể xảy ra?

**Đáp án:** case hẹp bị dominated bởi case rộng, có thể gây lỗi biên dịch. Tạo ví dụ hai case, sửa thứ tự và giữ test hành vi sau khi biên dịch lại.

**Bài 6 — Null selector.** Với `switch(candidate)` chỉ có `case Shipment(...)` và `default`, chuyện gì xảy ra nếu `candidate == null`?

**Đáp án:** thường ném `NullPointerException`. Nếu hợp đồng cho phép null, thêm `case null` rồi test nhánh riêng; không giả định `default` là null fallback.

**Bài 7 — MatchException.** Trong ví dụ `Fragile`, làm thế nào phân biệt lỗi accessor với một mẫu không khớp thông thường?

**Đáp án:** chạy test nhỏ chỉ có `Fragile(var value)`; nếu accessor ném lỗi trong lúc matching, bắt `MatchException` bao quanh phép matching và kiểm tra `getCause()` là `IllegalStateException`. Mismatch thường chỉ trả false hoặc đi case khác.

**Bài 8 — Test xanh giả.** Tại sao một unit test chỉ gọi `fixed(blank)` mà không assert lại yếu?

**Đáp án:** nó không biết giá trị nào đúng. Phương thức có thể trả `"ship:"` mà test vẫn không báo lỗi. Cần `assertEquals("destination:missing", fixed(blank))`.

**Bài 9 — Bug sau refactor.** Một hàm vừa kiểm tra `queue.poll() instanceof Shipment` vừa cast lần `queue.poll()` kế tiếp. Đổi sang pattern variable có thể bảo toàn behavior không?

**Đáp án:** không chắc, vì số lần gọi `poll()` đổi từ hai thành một và dữ liệu lấy ra có thể khác. Phải kiểm thử/đánh giá riêng phần thay đổi side effect thay vì gọi đó là refactor chỉ đổi cú pháp.

**Bài 10 — Bug triage.** Khi nào nên dùng compile test thay vì test runtime?

**Đáp án:** khi lỗi là dominance, exhaustiveness hoặc flow scope khiến mã không biên dịch. Tối giản khai báo type và case để compiler cung cấp lỗi trực tiếp; chỉ kiểm thử runtime sau khi có mã hợp lệ.

## 19. Checklist mang đi sử dụng

Trước khi kết luận đã cô lập và sửa một lỗi pattern matching, hãy kiểm tra:

- [ ] Có một input nhỏ **tái hiện** chính xác triệu chứng không?
- [ ] Expected được lấy từ **hợp đồng nghiệp vụ**, không phải chép từ actual?
- [ ] Đã phân biệt selector type, nested record shape, guard và case body?
- [ ] Có test **selector null**, **record con null**, **component null** khi mô hình có thể gặp chúng?
- [ ] Có phân biệt compile error, mismatch bình thường và exception trong matching?
- [ ] Đã kiểm tra thứ tự case, dominance và tính exhaustive nếu dùng `switch`?
- [ ] Đã tránh phụ thuộc nguồn dữ liệu thay đổi, thời gian, random hoặc I/O không kiểm soát?
- [ ] Bản sửa có regression test từng đỏ nay xanh, cộng test đối chứng non-bug?
- [ ] Test có assert output/exception/side effect thực sự, không chỉ gọi phương thức?
- [ ] Đã chạy bằng đúng phiên bản Java mà code sử dụng?

**Kết luận:** Test nhỏ là công cụ cô lập nguyên nhân, không chỉ là một phiên bản ít dòng của test lớn. Với Java pattern matching, tách **kiểu → cấu trúc record → giá trị thành phần → guard → nhánh và kết quả** giúp xác định lỗi ở đâu, tránh sửa nhầm và tạo regression test có ý nghĩa.

**Tài liệu chính thức:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Patterns and Pattern Matching (`14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification 21 — switch statement (`14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
