# Yield trong switch expression — Java Core Pattern Matching

## 1. Yield là gì?

Trong Java, **`switch expression`** là một biểu thức **tính ra một giá trị**. Giá trị đó có thể được gán cho biến, truyền vào một phương thức hoặc được phương thức khác `return`. Khi một nhánh `switch expression` chỉ cần một biểu thức, Java cho phép viết ngắn:

~~~java
String label = switch (code) {
    case 200 -> "OK";
    case 404 -> "NOT_FOUND";
    default -> "UNKNOWN";
};
~~~

Nhưng một nhánh thường phải làm nhiều việc: tính biến trung gian, gọi phương thức, dùng `if` hoặc chuẩn hóa dữ liệu. Với nhánh mũi tên có **block** `{ ... }`, ta dùng **`yield expression;`** để chỉ ra **giá trị mà nhánh cung cấp cho `switch expression`**:

~~~java
String label = switch (code) {
    case 200 -> {
        String message = "OK";
        yield message.toLowerCase();
    }
    default -> "UNKNOWN";
};
~~~

Với `code == 200`, `switch expression` có giá trị `"ok"`. Lệnh `yield message.toLowerCase();` **không kết thúc phương thức bao quanh**; nó kết thúc việc đánh giá `switch expression` hiện tại, trả giá trị cho nơi đang sử dụng biểu thức.

**Mốc phiên bản:** `switch expression` và `yield` chính thức từ **Java 14**; Java 17 sử dụng bình thường, không cần bật preview. **Pattern matching for switch** (nhãn `case String s`, `when` và các pattern khác) chính thức từ **Java 21**. Hai tính năng có quan hệ nhưng không ra đời cùng phiên bản.

## 2. Switch statement khác switch expression ở điểm nào?

Trong Java truyền thống, `switch` thường là một **statement**: mỗi case thực hiện câu lệnh hoặc hiệu ứng, không tự tạo ra một giá trị chung. `switch expression` được viết để biểu diễn một phép tính có kết quả.

| Tiêu chí | Switch statement | Switch expression |
| --- | --- | --- |
| Mục đích | Chạy câu lệnh/hiệu ứng | Tạo ra một giá trị |
| Cách dùng | Đứng độc lập như statement | Gán biến, làm đối số, dùng trong `return`... |
| `break;` | Có thể thoát statement | Không thay thế được `yield` |
| `yield result;` | Không dùng trực tiếp cho switch statement thuần túy | Chuyển giá trị cho switch expression |
| `case X -> expression` | Statement dạng rule có thể chứa statement expression phù hợp | Nhánh expression tạo ra giá trị |
| `case X -> { ... }` | Block chứa các statement | Block phải có đường đi cung cấp giá trị qua `yield` hoặc kết thúc đột ngột hợp lệ |
| Đầy đủ các trường hợp | Không phải mọi switch statement đều cần exhaustive | **Bắt buộc exhaustive** |

Hai cách làm cùng một việc:

~~~java
// Giả sử code là biến int đã khai báo.
String oldLabel;
switch (code) {
    case 0:
        oldLabel = "ZERO";
        break;
    default:
        oldLabel = "OTHER";
        break;
}

String newLabel = switch (code) {
    case 0 -> "ZERO";
    default -> "OTHER";
};
~~~

Đây là **mã minh họa** đặt trong một phương thức Java. Ở ví dụ thứ nhất, `break;` điều khiển kết thúc switch statement. Ở ví dụ thứ hai, **giá trị của toàn bộ switch expression** được gán trực tiếp cho `newLabel`.

Đừng xác định statement/expression chỉ dựa trên sự xuất hiện của mũi tên `->`: Java cũng có switch statement dùng rule `->`. Hãy xem **switch có được sử dụng như một giá trị** hay không.

## 3. Ba cách biểu diễn giá trị của nhánh

### 3.1. Một biểu thức sau dấu mũi tên

~~~java
String outcome = switch (status) {
    case 0 -> "NEW";
    case 1 -> "ACTIVE";
    default -> "UNKNOWN";
};
~~~

Mỗi biểu thức bên phải `->` chính là kết quả của nhánh, nên **không viết `yield`**. Đây là cách ưu tiên khi logic ngắn gọn.

### 3.2. Block sau dấu mũi tên và yield

~~~java
String outcome = switch (status) {
    case 0 -> "NEW";
    case 1 -> {
        String prefix = "ACT";
        String suffix = "IVE";
        yield prefix + suffix;
    }
    default -> "UNKNOWN";
};
~~~

Một **block** khác với một **expression**: block chứa nhiều statement nhưng không tự có giá trị như biểu thức. `yield prefix + suffix;` truyền kết quả `"ACTIVE"` cho switch expression.

Đúng:

~~~java
case 1 -> {
    yield "ACTIVE";
}
~~~

Sai nếu viết trực tiếp `yield` sau `->` mà không có block:

~~~java
case 1 -> yield "ACTIVE"; // COMPILE ERROR
~~~

Có thể sửa thành `case 1 -> "ACTIVE";` hoặc `case 1 -> { yield "ACTIVE"; }`.

Block có biểu thức cuối nhưng không yield cũng không hợp lệ:

~~~java
case 1 -> {
    String text = "ACTIVE";
} // COMPILE ERROR: block kết thúc bình thường mà không yield
~~~

Java không tự coi giá trị của biến vừa gán trong block là giá trị của switch expression.

### 3.3. Nhóm case dùng dấu hai chấm

Switch expression cũng chấp nhận cú pháp `case X:` truyền thống:

~~~java
String outcome = switch (status) {
    case 0:
        yield "NEW";
    case 1:
        yield "ACTIVE";
    default:
        yield "UNKNOWN";
};
~~~

Ở đây `yield` cần thiết để giá trị của switch expression được xác định. `case:` có thể có **fall-through**:

~~~java
String label = switch (code) {
    case 1:
    case 2:
        yield "SMALL";
    default:
        yield "OTHER";
};
~~~

Với `code` bằng 1 hoặc 2, kết quả đều là `"SMALL"`. Nếu không cần fall-through, cú pháp `case 1, 2 -> "SMALL";` thường dễ đọc hơn.

**Không dùng `break "SMALL";`.** Các bản preview cũ từng có cú pháp khác, nhưng Java 17/21 chính thức dùng **`yield value;`** khi cần trả giá trị từ nhánh colon của switch expression.

## 4. Chương trình Java 17 hoàn chỉnh

Lưu thành **`YieldBasicsDemo.java`**:

~~~java
public class YieldBasicsDemo {
    enum Status { NEW, ACTIVE, SUSPENDED, CLOSED }

    static String message(Status status) {
        return switch (status) {
            case NEW -> "Awaiting activation";
            case ACTIVE -> {
                String label = "Running";
                yield label + " now";
            }
            case SUSPENDED, CLOSED -> {
                String suffix = status == Status.SUSPENDED
                        ? "Paused" : "Finished";
                yield suffix;
            }
        };
    }

    static int normalizedScore(int score) {
        return switch (score / 10) {
            case 10, 9 -> 5;
            case 8 -> {
                int result = 4;
                yield result;
            }
            case 7 -> 3;
            default -> 1;
        };
    }

    static String code(int value) {
        return switch (value) {
            case 0:
                yield "ZERO";
            case 1:
            case 2:
                yield "SMALL";
            default:
                yield "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(message(Status.NEW));
        System.out.println(message(Status.ACTIVE));
        System.out.println(message(Status.SUSPENDED));
        System.out.println(message(Status.CLOSED));
        System.out.println(normalizedScore(95));
        System.out.println(normalizedScore(82));
        System.out.println(normalizedScore(61));
        System.out.println(code(0));
        System.out.println(code(2));
        System.out.println(code(4));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac YieldBasicsDemo.java
java YieldBasicsDemo
~~~

Đầu ra:

~~~text
Awaiting activation
Running now
Paused
Finished
5
4
1
ZERO
SMALL
OTHER
~~~

Ý nghĩa:

1. `NEW -> "Awaiting activation"` tạo giá trị trực tiếp bằng arrow expression, không cần yield.
2. `ACTIVE -> { ... yield ...; }` có block tính `label`, rồi `yield` trả chuỗi `"Running now"`.
3. Nhánh `SUSPENDED, CLOSED` gộp hai enum constants, tính `suffix` từ `status` và yield kết quả.
4. `normalizedScore` cho thấy `yield` **không giới hạn ở String**: trong trường hợp `score = 82`, nhánh `case 8` trả `int` là 4.
5. Phương thức `code` dùng nhóm nhãn `case:`, bao gồm fall-through của `case 1` sang `case 2`.

`message` không cần `default` vì đã bao phủ **tất cả hằng của enum Status**. Tuy vậy, nếu truyền `status == null` vào switch trên enum này thì sẽ ném `NullPointerException`; điều đó **khác** với yêu cầu exhaustiveness cho các hằng enum không null.

## 5. Yield, return, break: ba ý nghĩa khác nhau

Dễ nhầm nhất là thấy cả `yield` và `return` trong cùng một phương thức:

~~~java
static String classify(int code) {
    return switch (code) {
        case 200 -> {
            String result = "OK";
            yield result;
        }
        default -> "OTHER";
    };
}
~~~

Ở đây có **hai lần truyền giá trị ở hai mức khác nhau**:

- `yield result;` làm cho **switch expression** được chọn có kết quả `"OK"`.
- `return switch (...) { ... };` làm cho **phương thức `classify`** trả kết quả của biểu thức switch cho bên gọi.

Nếu switch expression ở vế phải của phép gán, chương trình vẫn tiếp tục sau phép gán:

~~~java
static String decorate(int code) {
    String result = switch (code) {
        case 200 -> {
            yield "OK";
        }
        default -> "OTHER";
    };
    return "[" + result + "]";
}
~~~

Với `code = 200`, phương thức này trả `"[OK]"`: `yield` chỉ kết thúc việc đánh giá switch expression, sau đó dòng `return` cuối vẫn chạy.

**Mã sai có chủ ý:**

~~~java
static int invalidBreak(int code) {
    return switch (code) {
        case 1 -> {
            break; // COMPILE ERROR: không dùng break để thoát switch expression
        }
        default -> 0;
    };
}
~~~

~~~java
static int invalidReturn(int code) {
    return switch (code) {
        case 1 -> {
            return 10; // COMPILE ERROR: return không rời switch expression
        }
        default -> 0;
    };
}
~~~

Nếu cần kết quả 10, hãy viết `case 1 -> 10;` hoặc `case 1 -> { yield 10; }`. Nếu thật sự muốn một nhánh kết thúc phương thức sớm theo cách riêng, cân nhắc cấu trúc `if` hoặc switch statement.

Ngoài ra, `yield` là **yield statement** với cú pháp `yield expression;`, không phải hàm để import hoặc API của một class. Java coi `yield` là *restricted identifier* có chức năng cú pháp cụ thể trong bối cảnh này.

## 6. Mọi đường đi phải yield hoặc kết thúc đột ngột hợp lệ

Một switch expression phải tạo ra giá trị. Với branch block, compiler kiểm tra **mọi đường điều khiển có thể chạy đến cuối block**.

Ví dụ hợp lệ với nhiều `yield`:

~~~java
static String grade(int score) {
    return switch (score / 10) {
        case 10, 9 -> "A";
        case 8 -> {
            if (score >= 85) {
                yield "B+";
            }
            yield "B";
        }
        default -> "OTHER";
    };
}
~~~

Khi score thuộc 80–89, một trong hai `yield` chắc chắn được thực hiện. Việc có nhiều yield trong cùng block không sai; mỗi đường đi chỉ thực hiện một lệnh yield.

Một nhánh có thể **ném ngoại lệ** thay vì tạo giá trị:

~~~java
static int points(int level) {
    return switch (level) {
        case 1 -> {
            yield 10;
        }
        case 2 -> {
            throw new IllegalArgumentException("invalid level");
        }
        default -> 0;
    };
}
~~~

Với `level == 2`, caller nhận ngoại lệ; switch expression không tạo giá trị trong đường đi đó. Điều này hợp lệ vì nhánh **kết thúc đột ngột** bằng `throw`. Ngược lại, một block `case -> { ... }` **chạy đến hết mà không yield hay throw** là lỗi compile time.

Không nên nhầm “mọi block phải chứa yield” với quy tắc thật. **Một nhánh chỉ có expression không cần yield; một nhánh ném ngoại lệ cũng không cần yield.** Yêu cầu là những đường đi hoàn tất bình thường của switch expression phải có giá trị phù hợp.

## 7. Exhaustiveness: yield không thay cho default

`yield` chỉ xác định **giá trị trả về từ nhánh đã chọn**, không khiến các trường hợp còn thiếu tự nhiên được xử lý.

Ví dụ:

~~~java
static String size(int count) {
    return switch (count) {
        case 0 -> "empty";
        case 1 -> "single";
        default -> {
            String text = count > 1 ? "multiple" : "invalid";
            yield text;
        }
    };
}
~~~

Với selector kiểu mở như `int`, `default` giúp bao phủ các số còn lại. Với enum có tất cả các constants đã liệt kê, compiler có thể chứng minh exhaustiveness mà không cần default, như ví dụ `YieldBasicsDemo`.

Trong Java 21, tập type patterns trên sealed hierarchy cũng có thể bảo đảm exhaustiveness khi đủ các kiểu con thích hợp. Dù thế nào, các case còn phải **applicable**, không bị che bởi case trước và phù hợp với quy tắc của switch.

Một switch expression có đầy đủ `yield` trong các block vẫn **không hợp lệ** nếu không bao phủ tất cả trường hợp đầu vào hợp lệ. Hai loại lỗi độc lập:

- **Thiếu yield**: một nhánh block có thể hoàn tất bình thường mà không sinh giá trị.
- **Thiếu exhaustiveness**: có trường hợp selector chưa được nhánh nào bao phủ.

## 8. Java 21: yield kết hợp switch pattern và when

Pattern matching for switch được chuẩn hóa trong **Java 21**, bao gồm type patterns, guard `when` và xử lý `null` bằng `case null`.

Lưu thành **`YieldPatternDemo.java`**:

~~~java
public class YieldPatternDemo {

    static String describe(Object input) {
        return switch (input) {
            case null -> "NULL";

            case String s when s.isBlank() -> {
                yield "BLANK";
            }

            case String s -> {
                String cleaned = s.strip();
                yield "TEXT(" + cleaned.length() + "):" + cleaned;
            }

            case Integer n when n < 0 -> {
                String output = "NEGATIVE:" + n;
                yield output;
            }

            case Integer n -> "INT:" + n;

            default -> "OTHER:" + input.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("  \t  "));
        System.out.println(describe(" Java "));
        System.out.println(describe(-7));
        System.out.println(describe(4));
        System.out.println(describe(2.5));
    }
}
~~~

Lệnh trên **JDK 21**:

~~~bash
javac YieldPatternDemo.java
java YieldPatternDemo
~~~

Đầu ra chính xác:

~~~text
NULL
BLANK
TEXT(4):Java
NEGATIVE:-7
INT:4
OTHER:Double
~~~

Giải thích theo trình tự:

1. `case null` nhận selector null trực tiếp: kết quả `"NULL"`. Đây là nhãn đặc biệt của switch Java 21, không phải type pattern `instanceof`.
2. `case String s when s.isBlank()` chỉ chọn khi đầu vào là String và guard true. Block chứa `yield "BLANK";`. Nếu nhánh chỉ cần trả chuỗi này, có thể viết gọn `-> "BLANK";`.
3. `case String s` nhận những String còn lại. Pattern variable `s` hợp lệ trong block, dùng để `strip()`, rồi `yield` tạo giá trị của switch.
4. `case Integer n when n < 0` nhận số nguyên âm, block có biến trung gian rồi yield; `case Integer n` nhận những số nguyên còn lại.
5. `default` nhận kiểu khác; nhờ có `case null`, nhánh này không chạy với null nên lệnh `input.getClass()` không gây NPE do null.

**Thứ tự các case quan trọng.** Nếu đặt `case String s` trước `case String s when s.isBlank()`, nhánh đặc thù phía sau bị **dominated** — mọi String đã bị nhánh tổng quát bắt — và compiler từ chối. `yield` không giải quyết lỗi dominance; phải đưa nhánh có guard lên trước.

**Null cũng cần xử lý rõ.** Trong Java 21, một switch trên tham chiếu mà không có `case null` thường ném `NullPointerException` khi selector là null, **dù có `default`**. `default -> { yield ...; }` không thay thế `case null`.

## 9. Kiểu dữ liệu của yield phải phù hợp kiểu switch expression

Trong một switch expression, giá trị của các nhánh `-> expression` và biểu thức của các `yield expression;` đều tham gia kiểm tra kiểu. Chúng phải tương thích với **ngữ cảnh kiểu** nơi đặt switch expression.

Ví dụ:

~~~java
int priority = switch (category) {
    case "HIGH" -> 10;
    case "MEDIUM" -> {
        int base = 3;
        yield base + 2;
    }
    default -> 0;
};
~~~

Giả sử `category` là biến String đã khai báo. Kết quả các nhánh tương thích với `int`, nên có thể gán cho `int priority`.

Mã **cố ý sai**:

~~~java
int count = switch (category) {
    case "A" -> 1;
    default -> {
        yield "unknown"; // COMPILE ERROR: String không phù hợp int
    }
};
~~~

`yield` không phải một phép ép kiểu tự do. Với giá trị kiểu tham chiếu, `yield null;` có thể hợp lệ nếu ngữ cảnh cho phép, nhưng sẽ truyền một **giá trị null thật sự** cho nơi dùng switch expression. Nếu kiểu kết quả là primitive như `int` thì không thể dùng null để thay số nguyên.

Các biến cục bộ tạo trong block của case không tự ra ngoài cùng switch:

~~~java
String display = switch (mode) {
    case 1 -> {
        String temporary = "alpha";
        yield temporary.toUpperCase();
    }
    default -> "other";
};
~~~

`temporary` chỉ ở trong block. Bên ngoài chỉ dùng được **`display`**, chứa giá trị đã yield.

## 10. Switch expression lồng nhau: yield thuộc về switch gần nhất

Ví dụ minh họa Java 17+:

~~~java
static String nested(int value) {
    return switch (value) {
        case 1 -> {
            String part = switch (value + 1) {
                case 2 -> {
                    yield "TWO";
                }
                default -> "OTHER";
            };
            yield "Outer:" + part;
        }
        default -> "NONE";
    };
}
~~~

- `nested(1)` trả `"Outer:TWO"`.
- `nested(0)` trả `"NONE"`.

`yield "TWO";` kết thúc **switch expression bên trong** `switch (value + 1)`, khiến `part` được gán `"TWO"`. Sau đó `yield "Outer:" + part;` kết thúc **switch expression bên ngoài**.

Vì vậy đừng hiểu `yield` như “thoát toàn bộ switch lồng nhau” hay “thoát khỏi phương thức”. Nó hướng đến switch expression bao quanh gần nhất. Cũng không thể đặt `yield` bên trong một lambda/method/initializer lồng trong switch rồi dùng nó để thoát khỏi switch expression ở ngoài các ranh giới đó.

## 11. Các lỗi phổ biến và cách sửa

| Tình huống | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `case 1 -> yield 10;` | Yield statement không phải expression trực tiếp sau mũi tên | `case 1 -> 10;` hoặc `case 1 -> { yield 10; }` |
| `case 1 -> { int x = 10; }` trong switch expression | Block có đường đi kết thúc mà không có giá trị | Thêm `yield x;` |
| `yield;` | Yield statement cần expression | `yield result;` |
| `break 10;` | Cú pháp cũ/không hợp lệ trên Java 17 và Java 21 | Dùng `yield 10;` |
| `break;` thay cho yield trong switch expression | Không cung cấp giá trị và không hợp lệ để thoát switch expression | `yield` hoặc `throw` |
| `return 10;` bên trong switch expression | Không được return từ bên trong switch expression | `yield 10;`; `return switch(...)` để trả khỏi method |
| Có `yield` nhưng vẫn thiếu nhánh | Yield không bảo đảm exhaustiveness | Bổ sung case/default cần thiết |
| `case String s` trước `case String s when ...` | Nhánh tổng quát che nhánh guard | Đặt case đặc thù lên trước |
| Dùng `case null`/pattern switch của Java 21 với Java 17 | Chưa là tính năng chính thức ở Java 17 | Dùng JDK 21+ |
| Dùng `yield` trong switch statement thông thường | Statement không tự tạo giá trị | Dùng statement và `break`; hoặc viết switch expression |

Đặc biệt, **`yield` không phải thay thế cho mọi `break` và `return`**. Nó chỉ phục vụ ngữ cảnh tạo giá trị từ switch expression.

## 12. Nên dùng yield thế nào trong mã thật?

**Một expression duy nhất:** dùng trực tiếp `-> expression`:

~~~java
case String s -> s.toUpperCase();
~~~

**Nhiều bước tính:** dùng `-> { ... yield ...; }`:

~~~java
case String s -> {
    String cleaned = s.strip();
    String result = "[" + cleaned + "]";
    yield result;
}
~~~

**Có phân nhánh bên trong case:** có thể có nhiều yield hợp lệ:

~~~java
case String s -> {
    if (s.isBlank()) {
        yield "(empty)";
    }
    yield s.strip();
}
~~~

Ba đoạn trên là **các nhánh minh họa của switch expression có type pattern Java 21**, không phải chương trình độc lập. Với một nhánh đơn giản, đừng thêm block và yield chỉ vì thích nhiều dòng. Với một nhánh phức tạp, block và yield giúp tách rõ các bước xử lý và giá trị trả về.

Đối với switch patterns, nên xử lý `case null` nếu cần, đặt các guard đặc thù trước nhánh tổng quát, kiểm tra tính exhaustive và bảo đảm mọi block hợp lệ. Không gộp lỗi dominance, lỗi null selector và lỗi thiếu yield thành một nguyên nhân: đó là ba quy tắc khác nhau.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Hai dạng sau đều hợp lệ trong một switch expression không?

~~~java
case 200 -> "OK";
~~~

~~~java
case 200 -> {
    yield "OK";
}
~~~

**Đáp án:** Có. Dạng đầu gọn hơn nếu nhánh chỉ cần một biểu thức.

**Câu 2.** Trong `return switch(code) { case 1 -> { yield 10; } default -> 0; };`, lệnh nào kết thúc switch expression, lệnh nào kết thúc phương thức?

**Đáp án:** `yield 10;` cung cấp giá trị cho switch expression; `return` đưa giá trị của switch expression ra ngoài phương thức.

**Câu 3.** Đoạn dưới có biên dịch không?

~~~java
int n = switch (code) {
    case 1 -> {
        int value = 10;
    }
    default -> 0;
};
~~~

**Đáp án:** Không. Block `case 1` kết thúc bình thường mà không yield. Cần thêm `yield value;`.

**Câu 4.** Trong Java 21, có thể đặt `case String s when s.isBlank()` sau `case String s` không?

**Đáp án:** Không. Nhánh String rộng che nhánh có guard; đổi thứ tự case.

**Câu 5.** Trong ví dụ switch lồng nhau, `yield "TWO";` trả cho switch nào?

**Đáp án:** Switch bên trong `switch (value + 1)`; switch bên ngoài vẫn cần một giá trị khác từ `yield "Outer:" + part;`.

## 14. Tham khảo đặc tả chính thức

- [Java Language Specification 21 — switch Expressions, mục 15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): cú pháp switch expression, kiểu, tính exhaustive và luồng điều khiển.
- [Java Language Specification 21 — The yield Statement, mục 14.21](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.21): cú pháp và ý nghĩa của `yield expression;`.
- [Java Language Specification 21 — The switch Statement, mục 14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): switch statement, switch rules, case labels.
- [Java Language Specification 21 — Patterns, mục 14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): pattern matching và các quy tắc liên quan.

**Ghi nhớ:** Với `switch expression`, `case ... -> expression` đã trực tiếp cho giá trị; khi cần block nhiều bước thì dùng `case ... -> { ... yield value; }`, hoặc `yield` trong nhánh colon. `yield` trả giá trị cho **switch expression gần nhất**, không thay `return` của phương thức hay `break` của switch statement. Trong Java 21, type patterns/`when` và `case null` làm cách chọn nhánh phong phú hơn, nhưng nguyên tắc `yield` vẫn như vậy.
