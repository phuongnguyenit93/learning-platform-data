# `return` hoặc `throw` trong `finally` che mất kết quả trước đó

Trong Java, khối `finally` thường được thực thi khi thoát khỏi cấu trúc `try`, cho dù luồng đang kết thúc bình thường, chuẩn bị `return`, hoặc đang lan truyền ngoại lệ. Đây là cơ chế quan trọng để dọn dẹp tài nguyên, nhưng cũng mang một rủi ro:

> **Nếu `finally` tự kết thúc bất thường bằng `return` hoặc `throw`, lý do hoàn tất đang chờ từ `try` hoặc `catch` bị thay thế bằng lý do mới của `finally`.**

Ví dụ, một phương thức định trả `10` nhưng `finally` lại `return 20;` thì caller nhận `20`. Một phương thức định ném `IllegalStateException("original")` nhưng `finally` lại ném `IllegalArgumentException("cleanup failed")` thì caller nhận **ngoại lệ mới**, không phải ngoại lệ gốc. Đây không chỉ là vấn đề phong cách code; nó có thể làm mất dấu lỗi, trả kết quả sai và khiến chương trình báo thành công dù thao tác thực sự đã thất bại.

## 1. Quy tắc nền tảng: lý do hoàn tất của `finally` có thể ghi đè lý do trước

Java phân biệt hai kiểu hoàn tất:

- **Hoàn tất bình thường (*normal completion*):** một khối chạy đến hết mà không chuyển điều khiển ra bằng `return`, `throw`, `break` hoặc `continue`.
- **Hoàn tất bất thường (*abrupt completion*):** quá trình rời khỏi khối do một nguyên nhân như `return`, `throw`, `break` hoặc `continue`.

Khi rời `try` hay `catch`, một khối `finally` tương ứng sẽ được thực thi theo quy tắc của ngôn ngữ. Lúc đó:

1. Nếu `finally` **hoàn tất bình thường**, lý do hoàn tất trước đó được giữ nguyên. Một `return` từ `try` tiếp tục trả kết quả; một ngoại lệ từ `try` tiếp tục lan truyền.
2. Nếu `finally` **hoàn tất bất thường**, lý do mới từ `finally` thay thế lý do hoàn tất trước đó, dù lý do trước là một giá trị trả về hay một ngoại lệ.

Ta có thể hình dung:

```text
try hoặc catch chuẩn bị hoàn tất với lý do R
                  │
                  ▼
              chạy finally
                  │
          ┌───────┴────────┐
          ▼                ▼
    finally bình thường  finally bất thường với lý do S
          │                │
          ▼                ▼
       giữ R              dùng S
                         (R bị bỏ)
```

Các trường hợp `R` hoặc `S` có thể là `return`, `throw`, `break` hoặc `continue`. Bài này tập trung vào **`return` và `throw` bên trong `finally`** vì chúng dễ tạo lỗi nghiêm trọng nhất: trả sai kết quả hoặc che khuất nguyên nhân thực sự.

## 2. Ma trận hành vi: `try` làm gì, `finally` làm gì?

| Kết quả từ `try` / `catch` | `finally` hoàn tất thế nào? | Kết quả mà caller nhìn thấy |
| --- | --- | --- |
| Chạy đến cuối bình thường | Chạy đến cuối bình thường | Tiếp tục luồng bình thường |
| `return A;` | Chạy đến cuối bình thường | Trả `A` |
| `throw E1;` | Chạy đến cuối bình thường | Ném `E1` |
| `return A;` | `return B;` | **Trả `B`**, `A` bị bỏ |
| `throw E1;` | `return B;` | **Trả `B`**, `E1` bị che |
| `return A;` | `throw E2;` | **Ném `E2`**, không trả `A` |
| `throw E1;` | `throw E2;` | **Ném `E2`**, `E1` bị che |
| Chạy đến cuối bình thường | `return B;` | Trả `B` |
| Chạy đến cuối bình thường | `throw E2;` | Ném `E2` |

Trong bảng, `A` và `B` chỉ là các giá trị minh họa; `E1` và `E2` là các ngoại lệ. “Bị che” có nghĩa rằng **nếu không được lưu bằng một cơ chế riêng, caller không còn nhận được lỗi hoặc kết quả trước đó**. Java không tự gắn `E1` thành `cause` hay *suppressed exception* của `E2` chỉ vì `finally` ném lỗi mới.

**Không nhầm:** một `finally` thông thường chỉ ghi log hoặc giải phóng tài nguyên rồi hoàn tất bình thường **không** tự làm mất giá trị trả về hay ngoại lệ từ `try`.

## 3. `return` trong `finally` ghi đè `return` ở `try`

Xét phương thức:

```java
static int wrongResult() {
    try {
        return 10;
    } finally {
        return 20;
    }
}
```

Đây là một **phương thức minh họa**, cần đặt trong một lớp Java. Kết quả `wrongResult()` là **`20`**.

Trình tự:

1. `try` đánh giá biểu thức `10` và chuẩn bị trả về.
2. Trước khi phương thức thực sự trả cho caller, Java chạy `finally`.
3. `finally` thực hiện `return 20;`, tạo **một lý do hoàn tất mới**.
4. Giá trị `10` đang chờ bị bỏ; caller nhận `20`.

Nhiều người tưởng `finally` chỉ “chạy thêm” sau khi đã `return` xong. Điều này sai: `finally` chạy **trước khi kết thúc lời gọi**, và có thể thay đổi kết quả hoàn tất.

Điều nguy hiểm là code có thể trông như đã xử lý đúng trong `try`, nhưng một `return` vô tình nằm trong nhánh dọn dẹp sẽ khiến kết quả không phản ánh thao tác chính.

### `return` trong `catch` cũng có thể bị ghi đè

```java
static String fallback() {
    try {
        throw new IllegalArgumentException("invalid");
    } catch (IllegalArgumentException ex) {
        return "recovered";
    } finally {
        return "overridden";
    }
}
```

Caller nhận `"overridden"`, không phải `"recovered"`. `finally` được thực thi khi handler `catch` chuẩn bị trả về, và `return` cuối cùng thay thế giá trị của handler.

Nếu `finally` không có `return`/`throw` gây hoàn tất bất thường, `"recovered"` sẽ được giữ nguyên.

## 4. `return` trong `finally` có thể nuốt luôn ngoại lệ

Ví dụ:

```java
static int dangerouslySilent() {
    try {
        throw new IllegalStateException("database write failed");
    } finally {
        return 0;
    }
}
```

Đây là phương thức minh họa. **Kết quả là `0`**; caller không nhận `IllegalStateException`.

Diễn biến:

1. Thao tác trong `try` ném `IllegalStateException`.
2. Java chuẩn bị cho ngoại lệ lan ra caller.
3. `finally` chạy và gặp `return 0;`.
4. `return` mới thay thế hoàn tất do `throw`. Ngoại lệ đang chờ bị bỏ.

Đây là một **anti-pattern nguy hiểm**: phương thức có thể báo một giá trị bình thường, thậm chí được diễn giải là thành công, trong khi thao tác chính thật ra đã thất bại.

Nếu caller dùng giá trị `0` như số bản ghi đã xử lý hoặc mã kết quả, lỗi ghi cơ sở dữ liệu có thể bị che mất hoàn toàn. Các cơ chế ở tầng trên như retry, transaction rollback dựa vào exception, logging lỗi hoặc cảnh báo giám sát có thể không nhận được tín hiệu cần thiết.

**Không dùng `return` trong `finally` để đưa ra giá trị mặc định khi `try` lỗi.** Nếu muốn fallback, đặt logic trong `catch` phù hợp, xác minh rằng việc phục hồi là hợp lệ, rồi trả một kết quả có nghĩa.

## 5. `throw` trong `finally` ghi đè giá trị đang chuẩn bị trả

```java
static int resultLost() {
    try {
        return 42;
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

Ở đây, caller **không nhận `42`**. Thay vào đó, nó nhận `IllegalStateException("cleanup failed")`.

Điều này có thể xảy ra ngay cả khi phần xử lý chính thành công: một thao tác giải phóng tài nguyên thất bại trong `finally` làm toàn bộ lời gọi kết thúc bằng ngoại lệ. Đôi khi đó là chính sách hợp lệ vì đóng/ghi dữ liệu cuối cùng không thành công, nhưng cần quyết định có chủ đích. Không được suy luận rằng có `return` trong `try` thì phương thức chắc chắn trả về.

Một điểm khác: **biểu thức trả về đã được đánh giá trước khi `finally` chạy**, nhưng kết quả vẫn có thể không đến được caller nếu `finally` ném ngoại lệ mới.

## 6. `throw` trong `finally` che khuất một ngoại lệ trước đó

```java
static void originalErrorLost() {
    try {
        throw new IllegalArgumentException("invalid request");
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

Ngoại lệ mà caller nhận là **`IllegalStateException("cleanup failed")`**. `IllegalArgumentException("invalid request")` không tự động xuất hiện trong `getCause()` hay `getSuppressed()` của ngoại lệ mới.

Hãy phân biệt:

- **Ngoại lệ chính của thao tác:** phát sinh khi xử lý yêu cầu, ví dụ dữ liệu đầu vào sai.
- **Ngoại lệ trong dọn dẹp:** phát sinh khi gọi `close()`, ghi log, giải phóng tài nguyên hoặc một bước cleanup khác.
- **Ngoại lệ mà caller quan sát được:** với `finally` thông thường ném lỗi mới, thường là **ngoại lệ cleanup**, vì nó thay thế sự cố chính.

Khi xem stack trace, người điều tra có thể chỉ thấy vị trí cleanup và tin nhầm cleanup là sự cố đầu tiên. Điều này rất tốn công trong các hệ thống có nhiều tầng `try-catch-finally`.

### `finally` không tự bảo toàn `cause`

Giả sử:

```java
try {
    throw new IllegalArgumentException("original");
} finally {
    throw new IllegalStateException("replacement");
}
```

Không có quy tắc tự động gắn `IllegalArgumentException` vào `getCause()` của `IllegalStateException`. Muốn bảo toàn quan hệ nguyên nhân, mã phải **chủ động** giữ nguyên đối tượng hoặc dùng cấu trúc có cơ chế thích hợp như `try-with-resources`.

Điều này khác với trường hợp lập trình viên chủ động viết:

```java
throw new IllegalStateException("higher-level failure", original);
```

Ở câu thứ hai, `original` là một biến `Throwable` đã được lưu hợp lệ ở phạm vi hiện tại. Chính constructor nhận `cause` tạo quan hệ nguyên nhân, không phải vì câu lệnh được viết trong `finally`.

## 7. Ví dụ Java 17+ hoàn chỉnh: bốn cách ghi đè kết quả

Lưu chương trình sau thành **`FinallyOverrideDemo.java`**. Mọi thông điệp và kiểu lỗi được kiểm soát, nên stdout có thể dự đoán chính xác.

```java
public class FinallyOverrideDemo {

    static int returnOverReturn() {
        try {
            System.out.println("try A: return 10");
            return 10;
        } finally {
            System.out.println("finally A: return 20");
            return 20;
        }
    }

    static int returnOverThrow() {
        try {
            System.out.println("try B: throw original");
            throw new IllegalStateException("original");
        } finally {
            System.out.println("finally B: return 30");
            return 30;
        }
    }

    static int throwOverReturn() {
        try {
            System.out.println("try C: return 40");
            return 40;
        } finally {
            System.out.println("finally C: throw cleanup");
            throw new IllegalArgumentException("cleanup");
        }
    }

    static void throwOverThrow() {
        try {
            System.out.println("try D: throw original");
            throw new IllegalStateException("original");
        } finally {
            System.out.println("finally D: throw replacement");
            throw new IllegalArgumentException("replacement");
        }
    }

    static int safeFinally() {
        int value = 7;
        try {
            System.out.println("try E: return 7");
            return value;
        } finally {
            value = 8;
            System.out.println("finally E: local value is " + value);
        }
    }

    public static void main(String[] args) {
        System.out.println("A result=" + returnOverReturn());
        System.out.println("B result=" + returnOverThrow());

        try {
            System.out.println("C result=" + throwOverReturn());
        } catch (IllegalArgumentException ex) {
            System.out.println("C caught=" + ex.getMessage());
        }

        try {
            throwOverThrow();
        } catch (IllegalArgumentException ex) {
            System.out.println("D caught=" + ex.getMessage());
            System.out.println("D cause=" + ex.getCause());
            System.out.println(
                    "D suppressed=" + ex.getSuppressed().length);
        }

        System.out.println("E result=" + safeFinally());
    }
}
```

Biên dịch/chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 FinallyOverrideDemo.java
java FinallyOverrideDemo
```

**Stdout chính xác:**

```text
try A: return 10
finally A: return 20
A result=20
try B: throw original
finally B: return 30
B result=30
try C: return 40
finally C: throw cleanup
C caught=cleanup
try D: throw original
finally D: throw replacement
D caught=replacement
D cause=null
D suppressed=0
try E: return 7
finally E: local value is 8
E result=7
```

### Giải thích từng trường hợp

**A — `return` đè `return`:** `try` định trả `10`, `finally` trả `20`. Caller thấy `20`.

**B — `return` nuốt `throw`:** ngoại lệ `IllegalStateException("original")` trong `try` không còn được lan ra; `finally` trả `30`. Caller nhận `30` như một kết quả bình thường.

**C — `throw` đè `return`:** `try` chuẩn bị trả `40`, nhưng `finally` ném `IllegalArgumentException("cleanup")`. Lời gọi không trả `40` nên dòng `"C result=..."` không được in; handler ngoài in `C caught=cleanup`.

**D — `throw` đè `throw`:** `try` ném `IllegalStateException("original")`, còn `finally` ném `IllegalArgumentException("replacement")`. Caller bắt lỗi thay thế; `getCause()` là `null` và danh sách `getSuppressed()` rỗng, chứng minh nguyên nhân gốc **không được Java tự động gắn vào** trong mẫu `try-finally` này.

**E — `finally` hoàn tất bình thường:** `try` đánh giá `value` thành `7` trước khi trả, `finally` chỉ gán biến cục bộ thành `8` rồi in. Vì `finally` không `return`/`throw`, kết quả `7` được giữ nguyên.

Ví dụ này cố ý trình bày các cách viết **không nên dùng trong ứng dụng thật** (A–D) để kiểm chứng quy tắc của Java. Hãy học hành vi, **không sao chép `return` hay `throw` vô điều kiện trong `finally`** vào mã nghiệp vụ.

## 8. Thứ tự đánh giá biểu thức `return` trước `finally`

Một điểm tinh tế: Java **đánh giá biểu thức của `return` trước**, rồi thực thi `finally`, rồi mới hoàn tất việc trả giá trị nếu `finally` không thay đổi lý do hoàn tất.

Ví dụ với kiểu nguyên thủy:

```java
static int primitiveSnapshot() {
    int n = 5;
    try {
        return n;
    } finally {
        n = 9;
    }
}
```

Kết quả là **`5`**. Không phải `9`, vì giá trị của biểu thức `return n` đã được lấy trước khi gán lại `n` trong `finally`.

### Với đối tượng có thể thay đổi, caller có thể thấy trạng thái mới

```java
static StringBuilder referenceResult() {
    StringBuilder builder = new StringBuilder("A");
    try {
        return builder;
    } finally {
        builder.append("B");
    }
}
```

Caller nhận một tham chiếu tới đối tượng `StringBuilder` **đã chứa `"AB"`**. Vì biểu thức `return builder` lưu **tham chiếu**, việc sửa trạng thái của đối tượng trước khi lời gọi hoàn tất vẫn nhìn thấy được qua tham chiếu đó.

Không mâu thuẫn với quy tắc kiểu nguyên thủy:

- Với `int`, giá trị `5` đã được tính và không bị biến cục bộ `n` thay đổi ngược lại.
- Với `StringBuilder`, tham chiếu đã được tính, nhưng đối tượng mà tham chiếu trỏ tới vẫn có thể bị sửa trong `finally`.
- Nếu `finally` chỉ **gán biến `builder` sang một đối tượng khác**, tham chiếu đang chờ trả về vẫn trỏ tới đối tượng đã được đánh giá ở biểu thức `return`.
- Nếu `finally` ném lỗi hoặc `return` khác, caller không nhận kết quả ban đầu, dù biểu thức đã được đánh giá.

### Biểu thức `return` tự ném ngoại lệ thì sao?

```java
static int expressionFails() {
    try {
        return Integer.parseInt("not-a-number");
    } finally {
        System.out.println("cleanup");
    }
}
```

Ở đây, `Integer.parseInt` ném `NumberFormatException` **trước khi có giá trị `int` để trả**. `finally` in `cleanup`, rồi ngoại lệ gốc tiếp tục lan nếu `finally` hoàn tất bình thường. Nếu `finally` lại `return 0;` thì `NumberFormatException` có thể bị nuốt như trường hợp B.

Nhờ vậy, cần phân biệt “đã đánh giá giá trị để trả” với “biểu thức `return` bị lỗi khi đánh giá”: cả hai đều là những đường thoát có thể đi qua `finally`.

## 9. `catch` và `finally`: handler cùng cấp có bắt được lỗi do `finally` ném không?

**Không.** Các nhánh `catch` của một cấu trúc `try-catch-finally` xử lý ngoại lệ thoát ra từ **phần thân `try`**. Chúng không quay lại bắt ngoại lệ mới ném từ `finally` của chính cấu trúc ấy.

Ví dụ:

```java
try {
    System.out.println("work completed");
} catch (IllegalStateException ex) {
    System.out.println("caught by sibling");
} finally {
    throw new IllegalStateException("cleanup failed");
}
```

Mã trên in `work completed` rồi ném `IllegalStateException` khỏi toàn bộ cấu trúc. Nhánh `catch (IllegalStateException)` cùng cấp **không chạy** cho lỗi được ném từ `finally`.

Nếu muốn xử lý lỗi dọn dẹp trong một phạm vi riêng, có thể đặt một `try-catch` **bao ngoài** cấu trúc:

```java
try {
    try {
        System.out.println("work completed");
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
} catch (IllegalStateException ex) {
    System.out.println("outer caught: " + ex.getMessage());
}
```

Kết quả:

```text
work completed
outer caught: cleanup failed
```

Ví dụ giải thích **ranh giới bắt lỗi**, không khuyến khích chủ động ném lỗi dọn dẹp chỉ để tầng ngoài bắt. Nếu cleanup có thể lỗi, cần chính sách quản lý tài nguyên phù hợp.

## 10. `finally` ở nhiều tầng: lý do hoàn tất có thể bị thay thế nhiều lần

Với `try-finally` lồng nhau, mỗi khối `finally` có cơ hội giữ hoặc thay thế lý do hoàn tất mà nó nhận được.

```java
static int nestedReturns() {
    try {
        try {
            return 1;
        } finally {
            return 2;
        }
    } finally {
        return 3;
    }
}
```

Kết quả cuối cùng là **`3`**:

1. `try` trong chuẩn bị trả `1`.
2. `finally` trong thay thành `return 2`.
3. Toàn bộ cấu trúc trong đang chuẩn bị trả `2`.
4. `finally` ngoài thay tiếp thành `return 3`.

Đây là một ví dụ **cố ý thể hiện hành vi xấu**. Càng nhiều khối `finally` có điều khiển luồng bất thường, càng khó biết lý do kết thúc cuối cùng là gì. Các quy tắc tương tự áp dụng khi một hoặc nhiều `finally` ném ngoại lệ.

Trong code thực tế, hãy để `finally` thực hiện **dọn dẹp có giới hạn**, còn việc quyết định giá trị trả về hoặc lỗi nghiệp vụ nên nằm ở `try`, `catch` hay tầng điều phối phù hợp.

## 11. Vì sao `return`/`throw` trong `finally` làm log và giám sát sai lệch?

Giả sử có một job:

```java
int processJob() {
    try {
        writeDatabase();
        return 1;
    } finally {
        return 0;
    }
}
```

Đây là **đoạn chống mẫu**, vì `writeDatabase()` chỉ là phương thức giả định. Nếu database báo lỗi bằng ngoại lệ unchecked, `finally` vẫn trả `0`; hệ thống điều phối có thể coi đó là kết quả bình thường thay vì thất bại cần retry.

Các hậu quả thực tế gồm:

- **Mất nguyên nhân gốc:** hệ thống log tập trung không nhận được ngoại lệ chính, hoặc chỉ thấy lỗi cleanup ở lớp ngoài.
- **Phân loại sai trạng thái:** caller nhận giá trị bình thường, dù thao tác chính không hoàn tất.
- **Không thực hiện retry hoặc cảnh báo:** cơ chế retry dựa trên exception không kích hoạt nếu lỗi bị `return` nuốt.
- **Dữ liệu dễ bị sai lệch:** một phần tác động có thể đã xảy ra trước ngoại lệ; trả thành công giả không bảo đảm rollback.
- **Stack trace gây hiểu lầm:** khi `finally` ném ngoại lệ mới mà không giữ nguyên nhân, vị trí cleanup có thể trở thành dấu vết lỗi duy nhất mà caller thấy.

Chính vì vậy, nhiều quy tắc lint/static analysis cảnh báo `return` trong `finally`. Đây là cảnh báo có cơ sở ngữ nghĩa, không chỉ là sở thích định dạng.

## 12. Cách sửa: để `finally` hoàn tất bình thường

Một thiết kế cơ bản:

```java
static int compute() {
    try {
        int answer = 42;
        return answer;
    } finally {
        System.out.println("compute: finished");
    }
}
```

Caller nhận `42`, vì `finally` chỉ in một thông điệp rồi hoàn tất bình thường. Nếu `try` ném ngoại lệ thì lời gọi vẫn ném ngoại lệ đó, trừ khi chính câu lệnh ghi log ở `finally` phát sinh ngoại lệ mới.

Cấu trúc có `finally` là hữu ích khi cần một công việc luôn phải thử thực hiện vào cuối phạm vi, ví dụ cập nhật số liệu thống kê hoặc giải phóng trạng thái. Tuy nhiên, **không nên giả định mọi lệnh dọn dẹp đều chắc chắn không ném lỗi**. Nếu cleanup có khả năng thất bại, chính sách xử lý phải được thiết kế cụ thể.

### Đừng đặt fallback trong `finally`

Mã lỗi:

```java
static int parseOrDefault(String raw) {
    try {
        return Integer.parseInt(raw);
    } finally {
        return 0;
    }
}
```

Mã này luôn trả `0`, kể cả khi chuỗi là `"123"`. Nếu `raw` không hợp lệ, `NumberFormatException` cũng bị che.

Mã thể hiện chính sách fallback rõ hơn:

```java
static int parseOrDefault(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        return 0;
    }
}
```

Đây chỉ là một lựa chọn hợp lệ **nếu hợp đồng thật sự cho phép mặc định là `0` khi chuỗi không thể parse**. Nếu `0` không phân biệt được lỗi với giá trị hợp lệ, nên dùng kiểu kết quả tường minh, giá trị tùy chọn hoặc để lỗi lan lên.

Điểm quan trọng là fallback nằm trong **handler dành cho lỗi có thể phục hồi**, không nằm trong `finally` vốn chạy cả ở đường thành công.

## 13. Nếu cleanup có thể lỗi, dùng `try-with-resources` khi thích hợp

Với các tài nguyên triển khai `AutoCloseable`, Java cung cấp `try-with-resources` để xử lý việc đóng tài nguyên. Khi **thân `try` ném một ngoại lệ chính**, còn thao tác `close()` ném một ngoại lệ khác, Java lưu ngoại lệ lúc đóng vào **danh sách suppressed** của ngoại lệ chính theo quy tắc của `try-with-resources`.

Đó là một khác biệt quan trọng so với `try-finally` tự viết, nơi lỗi cleanup có thể thay thế lỗi chính.

### Ví dụ Java 17+ hoàn chỉnh: giữ lỗi chính và lỗi đóng

Lưu tệp **`SuppressedCloseDemo.java`**:

```java
public class SuppressedCloseDemo {

    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("resource: close");
            throw new IllegalStateException("close failed");
        }
    }

    static void work() {
        try (FailingResource resource = new FailingResource()) {
            System.out.println("body: fails");
            throw new IllegalArgumentException("body failed");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (IllegalArgumentException ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println("suppressed count: "
                    + ex.getSuppressed().length);
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed: "
                        + suppressed.getMessage());
            }
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 SuppressedCloseDemo.java
java SuppressedCloseDemo
```

**Stdout chính xác:**

```text
body: fails
resource: close
primary: body failed
suppressed count: 1
suppressed: close failed
```

### Vì sao lần này lỗi gốc không biến mất?

1. Phần thân `try` ném `IllegalArgumentException("body failed")`.
2. Khi rời `try-with-resources`, Java tự gọi `close()` của `FailingResource`.
3. `close()` ném `IllegalStateException("close failed")`.
4. Thay vì để lỗi `close()` tự động ghi đè lỗi từ thân `try`, cơ chế `try-with-resources` thêm lỗi đóng vào `getSuppressed()` của ngoại lệ chính.
5. Caller bắt `IllegalArgumentException` và có thể xem cả nguyên nhân chính lẫn lỗi đóng.

Vì ví dụ dùng lỗi unchecked và tài nguyên giả lập, đầu ra không phụ thuộc hệ điều hành hay file thật.

**Lưu ý quan trọng:** nếu phần thân `try` hoàn tất **bình thường** hoặc đang định `return` mà `close()` ném ngoại lệ, lỗi đóng vẫn có thể khiến lời gọi kết thúc bằng ngoại lệ, thay vì trả kết quả. `try-with-resources` không có nghĩa mọi lỗi cleanup đều bị bỏ qua; nó ưu tiên **bảo toàn lỗi chính khi cả phần thân và close đều ném lỗi**.

### Suppressed exception không giống `cause`

- **`cause`:** thể hiện một ngoại lệ làm nguyên nhân cho ngoại lệ khác, thường được lập trình viên gắn qua constructor `new X(message, cause)`.
- **`suppressed`:** danh sách lỗi phụ được gắn vào ngoại lệ chính, chẳng hạn lỗi khi đóng tài nguyên trong `try-with-resources`.
- `getCause()` không tự trả về lỗi đóng bị suppressed; cần `getSuppressed()`.
- Không có quy tắc tự động thêm suppressed exception khi lập trình viên viết một câu `throw` mới trong `finally` thông thường.

Có thể chủ động gọi `Throwable.addSuppressed(...)` trong một cơ chế cleanup phức tạp, nhưng phải giữ tham chiếu đúng tới ngoại lệ gốc và tránh xử lý sai các trường hợp lỗi khác. Trong phần lớn mã quản lý `AutoCloseable`, **ưu tiên `try-with-resources`** thay vì tự tái triển khai quy tắc suppression.

## 14. So sánh `try-finally` tự viết và `try-with-resources`

| Tiêu chí | `try-finally` gọi `close()` thủ công | `try-with-resources` |
| --- | --- | --- |
| Cách dọn dẹp | Lập trình viên tự gọi trong `finally` | Java tự gọi `close()` khi rời phạm vi |
| Có thể làm mất lỗi chính khi `close()` ném? | **Có**, nếu không tự quản lý lỗi | Cơ chế suppressed giúp giữ lỗi chính khi cả body và close lỗi |
| Đóng nhiều tài nguyên | Tự viết thứ tự và xử lý lỗi | Các tài nguyên được đóng theo **thứ tự ngược** với khai báo |
| Có cần `AutoCloseable`? | Không bắt buộc, tùy API | Có; tài nguyên phải là `AutoCloseable` |
| Có thể kết hợp `catch`/`finally` khác? | Có | Có |
| Có thay thế mọi rollback/giao dịch? | Không | Không |

Tuy nhiên `try-with-resources` **không thích hợp cho mọi cleanup**: có những công việc không sở hữu tài nguyên `AutoCloseable` hoặc cần quyết định xử lý lỗi đặc biệt. Khi dùng `finally` thủ công, hãy giữ khối rõ ràng và bảo đảm không vô tình thay thế kết quả/lỗi chính.

## 15. Trường hợp `finally` ném lỗi: xử lý ở đâu?

Một lỗi ném từ `finally` không được các nhánh `catch` **anh em cùng cấu trúc** bắt. Để xử lý nó ở caller:

```java
try {
    operationWithFinally();
} catch (IllegalStateException ex) {
    System.out.println("operation failed: " + ex.getMessage());
}
```

Đây là **khung minh họa**, giả định `operationWithFinally()` có thể ném `IllegalStateException`. Handler ngoài có thể bắt lỗi hiện đang lan lên, nhưng nếu lỗi gốc đã bị thay thế trong `finally` bên trong, **handler ngoài không thể tự khôi phục ngoại lệ gốc** chỉ bằng việc thêm một `catch`.

Cần giải quyết vấn đề ở **nơi dọn dẹp**, ví dụ:

- Sử dụng `try-with-resources` cho tài nguyên phù hợp.
- Nếu cleanup có thể thất bại mà không được phép che lỗi nghiệp vụ, giữ nguyên đối tượng lỗi chính và ghi nhận lỗi phụ theo chính sách cụ thể.
- Nếu lỗi cleanup nghiêm trọng đến mức thao tác phải coi là thất bại, cho phép ngoại lệ đó đi lên **có chủ đích** và thông tin chẩn đoán cần thiết, thay vì đặt `throw` thiếu cân nhắc trong `finally`.
- Không bao giờ im lặng nuốt mọi `Exception` trong cleanup chỉ để tránh che lỗi; việc bỏ qua lỗi phải được xác định và tài liệu hóa.

Ranh giới xử lý ở tầng ngoài quyết định phản hồi hệ thống, nhưng **không thể sửa hoàn toàn việc tầng dưới đã làm mất thông tin lỗi**.

## 16. Ngoại lệ và `return` từ `catch` cũng chịu cùng quy tắc

`finally` không chỉ đi cùng một `try` đơn. Với cấu trúc:

```java
static String recover() {
    try {
        throw new IllegalArgumentException("bad input");
    } catch (IllegalArgumentException ex) {
        return "fallback";
    } finally {
        System.out.println("cleanup");
    }
}
```

Caller nhận `"fallback"`; `finally` chỉ in và hoàn tất bình thường.

Nếu đổi `finally` thành:

```java
finally {
    throw new IllegalStateException("cleanup failed");
}
```

thì caller sẽ **nhận `IllegalStateException`, không nhận `"fallback"`**. Điều tương tự xảy ra nếu `catch` định ném lại ngoại lệ: một `return` khác trong `finally` có thể nuốt lỗi đang được ném lại.

Cách đọc chính xác là: **bất kỳ lý do hoàn tất đang chờ nào của `try` hoặc `catch` đều có thể bị thay thế bởi lý do mới do `finally` tạo ra**.

## 17. Có phải `finally` luôn được thực thi?

Theo luồng điều khiển Java thông thường, `finally` được thực thi khi rời `try` hoặc `catch`, kể cả khi có `return` hoặc ngoại lệ. Tuy vậy, **không nên coi đây là cam kết tuyệt đối trong mọi cách JVM/process kết thúc**.

Những tình huống có thể khiến `finally` không chạy như bạn kỳ vọng:

- `Runtime.getRuntime().halt(...)` kết thúc JVM trực tiếp.
- `System.exit(...)` bắt đầu quy trình tắt JVM, không bảo đảm chạy các `finally` ở thread đang hoạt động.
- Tiến trình bị hệ điều hành chấm dứt cưỡng bức, gặp sự cố nghiêm trọng hoặc máy mất điện.
- Thread bị kẹt trong thao tác không hoàn tất nên chưa rời `try` để tới `finally`.

Điều này không thay đổi quy tắc chính của bài: **khi `finally` thực sự được chạy theo luồng bình thường và nó hoàn tất bất thường, nó có thể thay thế kết quả đang chờ**.

## 18. `break` và `continue` trong `finally` cũng có thể thay đổi luồng

Ngoài `return` và `throw`, lý do hoàn tất bất thường còn có thể đến từ `break` hoặc `continue` trong vòng lặp.

Ví dụ cú pháp Java hợp lệ trong thân một phương thức:

```java
for (int i = 0; i < 2; i++) {
    try {
        System.out.println("try " + i);
        if (i == 0) {
            throw new IllegalStateException("failed");
        }
    } finally {
        continue;
    }
}
System.out.println("after loop");
```

**Stdout:**

```text
try 0
try 1
after loop
```

`continue` trong `finally` khiến vòng lặp chuyển sang lần lặp tiếp theo, làm ngoại lệ `IllegalStateException` ở lần đầu **không lan ra ngoài**. Đây là cùng một quy tắc “lý do hoàn tất mới thay thế lý do cũ”, dù không dùng `return` hay `throw`.

Đoạn mã này được đưa ra để **nhận diện anti-pattern**, không khuyến nghị viết `continue` hoặc `break` trong `finally`. Với các vòng lặp, các lệnh điều khiển luồng này còn làm hành vi khó đọc và dễ giấu lỗi.

## 19. Checklist phát hiện và sửa lỗi mất kết quả trong `finally`

Khi review một phương thức có `try-catch-finally`, hãy tự kiểm tra:

1. **`finally` có `return` không?** Nếu có, xác định nó đang thay thế giá trị trả về hay ngoại lệ nào. Thông thường nên chuyển chính sách trả về ra `try`/`catch`.
2. **`finally` có `throw` trực tiếp không?** Xem nó có che ngoại lệ đang lan truyền hay không, và caller có còn cách truy nguyên lỗi chính không.
3. **Các lời gọi trong `finally` có thể ném lỗi không?** `close()`, ghi log, callback cleanup, giải phóng tài nguyên đều có thể thất bại tùy API.
4. **`return` ở `try` đã được đánh giá trước khi dọn dẹp chưa?** Với kiểu nguyên thủy, sửa biến cục bộ trong `finally` không đổi giá trị đã tính; với đối tượng mutable, thay đổi trạng thái có thể vẫn quan sát được.
5. **`catch` có dự kiến trả fallback hoặc ném lại không?** Đảm bảo `finally` không âm thầm thay thế quyết định của handler.
6. **Có thể dùng `try-with-resources` không?** Nếu tài nguyên triển khai `AutoCloseable`, cơ chế này quản lý đóng và suppressed exceptions tốt hơn trong nhiều tình huống.
7. **Có đang log và xử lý cả lỗi chính lẫn lỗi dọn dẹp đúng chính sách không?** Tránh làm mất nguyên nhân chính nhưng cũng không giấu lỗi cleanup quan trọng.
8. **Có nested `finally` không?** Các lớp `finally` ngoài có thể thay thế tiếp kết quả do cấu trúc trong chuẩn bị trả.
9. **Có `break` hoặc `continue` trong `finally` không?** Chúng cũng thay đổi lý do hoàn tất và có thể che ngoại lệ.
10. **Đã kiểm thử đường lỗi chưa?** Ít nhất kiểm tra `return` trước `finally`, `throw` trước `finally`, cleanup thất bại, và tình huống body + close đồng thời thất bại.

## 20. Bài tập tự kiểm tra

**Bài A. Giá trị nào được trả về?**

```java
static int f() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
```

**Đáp án:** `2`. `return` của `finally` ghi đè `return` trước đó.

**Bài B. Lỗi có đi tới caller không?**

```java
static String f() {
    try {
        throw new IllegalStateException("fail");
    } finally {
        return "OK";
    }
}
```

**Đáp án:** caller nhận `"OK"`, ngoại lệ bị nuốt. Đây là ví dụ gây hiểu lầm nghiêm trọng nếu `"OK"` được xem là thành công.

**Bài C. Caller nhận lỗi nào?**

```java
static void f() {
    try {
        throw new IllegalArgumentException("original");
    } finally {
        throw new IllegalStateException("new");
    }
}
```

**Đáp án:** `IllegalStateException("new")`. Nếu mã không gắn `cause`/suppressed có chủ đích, lỗi `original` không tự xuất hiện trong ngoại lệ mới.

**Bài D. Biến bị sửa trong `finally`, kết quả trả về có đổi không?**

```java
static int f() {
    int x = 3;
    try {
        return x;
    } finally {
        x = 4;
    }
}
```

**Đáp án:** `3`, vì biểu thức trả về đã được đánh giá trước `finally` và không có `return` hoặc `throw` mới.

**Bài E. Tại sao đối tượng mutable có thể khác?**

```java
static StringBuilder f() {
    StringBuilder b = new StringBuilder("X");
    try {
        return b;
    } finally {
        b.append("Y");
    }
}
```

**Đáp án:** đối tượng được trả về chứa `"XY"`. Tham chiếu đã được đánh giá trước `finally` nhưng chính đối tượng đã bị sửa trong `finally`.

**Bài F. Thân `try-with-resources` và `close()` cùng ném lỗi thì sao?**

**Đáp án:** theo cơ chế `try-with-resources`, ngoại lệ của thân `try` thường là lỗi chính và lỗi từ `close()` được thêm vào danh sách suppressed. Có thể xem bằng `ex.getSuppressed()`; không mặc nhiên mất lỗi gốc như một `throw` mới từ `finally` thủ công.

**Bài G. Handler `catch` cùng cấp có xử lý ngoại lệ từ `finally` không?**

**Không.** Phải dùng handler ở phạm vi ngoài hoặc xử lý ngay trong cleanup; một handler cùng cấu trúc chỉ xử lý lỗi đến từ phần thân `try` mà nó bảo vệ.

**Bài H. Nested `finally` lần lượt trả `2` rồi `3`, kết quả cuối là gì?**

**`3`**, vì `return` ở `finally` ngoài thay thế kết quả đang chờ từ cấu trúc trong.

## Kết luận

Hãy ghi nhớ một quy tắc duy nhất:

**Khi `finally` hoàn tất bình thường, Java giữ lý do hoàn tất từ `try`/`catch`. Khi `finally` hoàn tất bất thường bằng `return` hoặc `throw`, lý do mới thay thế lý do trước đó.**

Hệ quả có thể là **trả sai giá trị**, **nuốt ngoại lệ gốc**, hoặc **chỉ còn ngoại lệ cleanup khiến việc chẩn đoán sai hướng**. Vì vậy, tránh `return` và các thao tác `throw` không có chủ đích trong `finally`; đưa quyết định kết quả vào `try`/`catch`, đặt cleanup ở phạm vi rõ ràng, và ưu tiên `try-with-resources` để quản lý tài nguyên `AutoCloseable` cùng các lỗi đóng tài nguyên bị suppressed.