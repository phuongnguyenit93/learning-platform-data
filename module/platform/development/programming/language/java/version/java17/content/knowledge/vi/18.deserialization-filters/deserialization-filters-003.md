# Trạng thái ALLOWED, REJECTED và UNDECIDED trong Java 17 Serialization Filtering

Java Object Serialization có thể tái tạo một object graph từ luồng byte. Khi ứng dụng đọc dữ liệu tuần tự hóa, các lớp trong object graph có thể được khởi tạo và một số logic của lớp có thể tham gia vào quá trình khôi phục dữ liệu. Nếu dữ liệu đến từ nguồn không đáng tin cậy, việc cho phép mọi lớp được giải tuần tự hóa có thể tạo ra rủi ro bảo mật và tiêu thụ tài nguyên ngoài dự kiến.

Java cung cấp **Serialization Filtering** thông qua `java.io.ObjectInputFilter`. Bộ lọc được gọi trong quá trình giải tuần tự hóa để kiểm tra lớp, độ sâu object graph, số lượng tham chiếu, kích thước luồng và độ dài mảng. Mỗi lần kiểm tra có thể trả về một trong ba trạng thái:

- **`ALLOWED`**: bộ lọc chấp nhận đối tượng hoặc điều kiện đang kiểm tra.
- **`REJECTED`**: bộ lọc từ chối; `ObjectInputStream` dừng quá trình đọc với lỗi phù hợp.
- **`UNDECIDED`**: bộ lọc không đưa ra quyết định cho lần kiểm tra này.

Điểm quan trọng nhất: **`UNDECIDED` không có nghĩa là từ chối**. Khi filter trả về `UNDECIDED`, Java có thể tiếp tục giải tuần tự hóa nếu không có filter khác từ chối. Vì vậy, cần hiểu rõ ba trạng thái, cách phối hợp filter và cách tạo chính sách allow-list rõ ràng.

Các API trong bài có mặt trong Java 17. Một số tiện ích như `allowFilter`, `rejectFilter`, `merge` và `rejectUndecidedClass` được bổ sung từ Java 17.

## 1. Serialization Filtering giải quyết vấn đề gì?

Java Serialization cho phép ghi object ra byte stream và đọc lại thành object. Ví dụ:

```java
import java.io.*;

record UserSnapshot(String username, int level)
        implements Serializable {
}

public class SerializationDemo {
    public static void main(String[] args) throws Exception {
        UserSnapshot original = new UserSnapshot("lan", 3);

        byte[] bytes;
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(buffer)) {
            output.writeObject(original);
            bytes = buffer.toByteArray();
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            Object restored = input.readObject();
            System.out.println(restored);
        }
    }
}
```

Đầu ra:

```text
UserSnapshot[username=lan, level=3]
```

Khi đọc một stream, ứng dụng không chỉ nhận một mảng byte thụ động. Java phải xác định lớp của các object được ghi trong stream, tạo object và khôi phục trạng thái của chúng theo quy tắc serialization.

Nếu ứng dụng đọc dữ liệu do người dùng, client, dịch vụ bên ngoài hoặc tệp không đáng tin cậy cung cấp, stream có thể chứa những lớp mà ứng dụng không dự định xử lý. Một object graph quá sâu, quá nhiều tham chiếu hoặc mảng quá lớn cũng có thể làm tiêu tốn tài nguyên.

Serialization Filtering cho phép ứng dụng đưa ra quyết định trong lúc đọc object graph:

- Lớp nào được chấp nhận.
- Lớp nào bị từ chối.
- Object graph có vượt giới hạn độ sâu hay không.
- Số tham chiếu có vượt giới hạn hay không.
- Tổng số byte đã đọc có vượt giới hạn hay không.
- Mảng đang được tạo có quá lớn hay không.

Filter không thay thế việc xác thực dữ liệu nghiệp vụ. Nó là một lớp kiểm soát dành cho quá trình Java Object Deserialization.

## 2. Ba trạng thái của `ObjectInputFilter.Status`

Enum `ObjectInputFilter.Status` nằm trong `java.io` và có đúng ba hằng số:

| Trạng thái | Ý nghĩa | Vai trò trong chính sách |
| --- | --- | --- |
| `ALLOWED` | Được chấp nhận. | Filter này đồng ý cho phép lần kiểm tra. |
| `REJECTED` | Bị từ chối. | Filter này phủ quyết lần kiểm tra; quá trình đọc bị chặn. |
| `UNDECIDED` | Chưa quyết định, không cho phép cũng không từ chối. | Filter này không có ý kiến; filter khác có thể đưa ra quyết định. |

### 2.1. `ALLOWED`

Trả `ALLOWED` khi filter xác định lớp hoặc điều kiện đang kiểm tra nằm trong chính sách được chấp nhận.

Ví dụ, một filter chỉ chấp nhận record DTO cụ thể:

```java
import java.io.ObjectInputFilter;

record UserSnapshot(String username, int level)
        implements java.io.Serializable {
}

ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == UserSnapshot.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Ở đây filter đưa ra quyết định chấp nhận khi lớp đang kiểm tra là `UserSnapshot`. Với lớp khác, filter chưa có ý kiến nên trả `UNDECIDED`.

`ALLOWED` có ý nghĩa trong kết quả của filter đang xét. Khi nhiều filter được kết hợp, một filter khác vẫn có thể trả `REJECTED` và khiến kết quả tổng thể bị từ chối.

### 2.2. `REJECTED`

Trả `REJECTED` khi đối tượng hoặc giới hạn tài nguyên vi phạm chính sách.

Ví dụ từ chối một lớp không nằm trong danh sách cho phép:

```java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == UserSnapshot.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

Nếu filter từ chối một lớp trong quá trình đọc, `ObjectInputStream` sẽ dừng thao tác giải tuần tự hóa và báo lỗi, thường là `InvalidClassException` với thông tin filter đã từ chối.

Không nên trả `REJECTED` chỉ vì filter hiện tại không hiểu một điều kiện nằm ngoài phạm vi của nó nếu filter khác còn chịu trách nhiệm đánh giá điều kiện đó. Trong trường hợp đó, `UNDECIDED` có thể là lựa chọn đúng.

### 2.3. `UNDECIDED`

`UNDECIDED` có nghĩa là filter không xác nhận chấp nhận và cũng không yêu cầu từ chối. Nó hữu ích khi một filter chỉ kiểm tra một phần chính sách.

Ví dụ, filter chỉ quan tâm đến proxy class:

```java
import java.lang.reflect.Proxy;
import java.io.ObjectInputFilter;

ObjectInputFilter noProxyFilter = info -> {
    Class<?> type = info.serialClass();

    if (type != null && Proxy.isProxyClass(type)) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Filter này chỉ từ chối proxy class. Với các lớp khác, nó trả `UNDECIDED` vì không có mục tiêu đánh giá chúng.

**Cảnh báo quan trọng:** nếu chỉ gắn `noProxyFilter` vào stream, các lớp khác không bị filter này từ chối. `UNDECIDED` không tự chuyển thành `REJECTED`. Nếu ứng dụng muốn chỉ cho phép một tập lớp xác định, cần một chính sách allow-list hoặc dùng `rejectUndecidedClass` phù hợp.

## 3. Điều gì xảy ra khi filter trả về từng trạng thái?

Trong quá trình deserialization:

- `REJECTED` khiến lần kiểm tra bị từ chối và thao tác đọc không tiếp tục bình thường.
- `ALLOWED` cho biết filter chấp nhận lần kiểm tra.
- `UNDECIDED` không chặn object; nếu không có filter nào từ chối, Java có thể tiếp tục giải tuần tự hóa.

Có thể ghi nhớ:

```text
                 ObjectInputFilter.checkInput(info)
                              |
               +--------------+--------------+
               |              |              |
               v              v              v
            ALLOWED        REJECTED       UNDECIDED
               |              |              |
               v              v              v
        Filter đồng ý     Từ chối đọc     Filter chưa có ý kiến
        cho phép          object graph    |
                              |            v
                              v        Filter khác có thể
                       InvalidClassException  đưa ra quyết định
                                           |
                                           v
                                  Nếu không bị từ chối,
                                  deserialization tiếp tục
```

Vì `UNDECIDED` có thể dẫn đến việc object vẫn được đọc, một filter chỉ trả `UNDECIDED` cho mọi lớp không tạo ra chính sách bảo vệ hữu hiệu. Filter phải thực sự trả `REJECTED` cho những trường hợp cần chặn, hoặc được kết hợp với filter có trách nhiệm quyết định phần còn lại.

## 4. `FilterInfo` cung cấp thông tin gì?

Phương thức chính của filter là:

```java
ObjectInputFilter.Status checkInput(
        ObjectInputFilter.FilterInfo filterInfo
);
```

`FilterInfo` cung cấp thông tin về object đang được xử lý và trạng thái của stream:

| Phương thức | Ý nghĩa |
| --- | --- |
| `serialClass()` | Lớp đang được kiểm tra; có thể là `null` nếu lần kiểm tra chỉ liên quan đến số liệu tài nguyên. |
| `arrayLength()` | Độ dài mảng nếu đang kiểm tra mảng; giá trị âm nếu không phải mảng. |
| `depth()` | Độ sâu hiện tại của object graph. |
| `references()` | Số lượng object reference đã được xử lý trong stream. |
| `streamBytes()` | Số byte đã được đọc từ stream tại thời điểm kiểm tra. |

Filter có thể đánh giá một hoặc nhiều thông tin này.

### 4.1. `serialClass()` có thể là null

Không được giả định `serialClass()` luôn trả về một lớp:

```java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == UserSnapshot.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

Khi `serialClass()` là `null`, filter vẫn có thể kiểm tra `depth()`, `references()` và `streamBytes()`. Do đó, nên đánh giá giới hạn tài nguyên trước khi trả `UNDECIDED` cho trường hợp không có lớp.

Không trả `null` từ `checkInput()`. Hợp đồng API yêu cầu một trong ba giá trị enum; trả `null` có thể dẫn đến `NullPointerException` hoặc hành vi không dự đoán được.

### 4.2. Độ sâu object graph

`depth()` cho biết độ sâu của cấu trúc object đang được đọc. Một graph quá sâu có thể làm tăng mức tiêu thụ stack hoặc tài nguyên.

Ví dụ:

```java
private static final long MAX_DEPTH = 20;

ObjectInputFilter depthFilter = info -> {
    if (info.depth() > MAX_DEPTH) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Filter này chỉ kiểm tra độ sâu. Nó không tự quyết định lớp nào được phép; có thể kết hợp với một filter khác để kiểm tra loại lớp.

### 4.3. Số lượng reference

`references()` cho biết số lượng tham chiếu object đã được xử lý. Một stream chứa số lượng object quá lớn có thể tiêu thụ bộ nhớ và thời gian xử lý.

```java
private static final long MAX_REFERENCES = 10_000;

ObjectInputFilter referenceFilter = info -> {
    if (info.references() > MAX_REFERENCES) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Giới hạn thực tế cần dựa trên kích thước object graph hợp lệ của ứng dụng. Không nên chọn một con số quá lớn chỉ để tránh lỗi với dữ liệu bất thường.

### 4.4. Kích thước stream

`streamBytes()` cho biết số byte đã được đọc. Có thể giới hạn lượng dữ liệu đầu vào:

```java
private static final long MAX_STREAM_BYTES = 1_000_000;

ObjectInputFilter byteLimitFilter = info -> {
    if (info.streamBytes() > MAX_STREAM_BYTES) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Giới hạn byte giúp giảm nguy cơ đọc một stream quá lớn. Nó không thay thế giới hạn kích thước file hoặc request ở tầng mạng; nên giới hạn dữ liệu trước khi tạo stream và tiếp tục kiểm tra trong filter.

### 4.5. Độ dài mảng

`arrayLength()` hữu ích khi dữ liệu tuần tự hóa chứa mảng. Mảng lớn có thể yêu cầu cấp phát bộ nhớ đáng kể.

```java
private static final long MAX_ARRAY_LENGTH = 100_000;

ObjectInputFilter arrayFilter = info -> {
    long length = info.arrayLength();

    if (length >= 0 && length > MAX_ARRAY_LENGTH) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Kiểm tra `length >= 0` để chỉ xử lý trường hợp hiện tại là mảng. Với object không phải mảng, `arrayLength()` không biểu diễn một độ dài mảng hợp lệ.

## 5. Kết hợp kiểm tra lớp và giới hạn tài nguyên

Một filter thực tế thường cần nhiều điều kiện. Ví dụ, chỉ chấp nhận một record DTO, đồng thời giới hạn độ sâu, số tham chiếu, byte và mảng:

```java
import java.io.ObjectInputFilter;

record UserSnapshot(String username, int level)
        implements java.io.Serializable {
}

public class UserSnapshotFilter {

    private static final long MAX_DEPTH = 20;
    private static final long MAX_REFERENCES = 2_000;
    private static final long MAX_STREAM_BYTES = 1_000_000;
    private static final long MAX_ARRAY_LENGTH = 100_000;

    static ObjectInputFilter createFilter() {
        return info -> {
            if (info.depth() > MAX_DEPTH
                    || info.references() > MAX_REFERENCES
                    || info.streamBytes() > MAX_STREAM_BYTES
                    || (info.arrayLength() >= 0
                        && info.arrayLength() > MAX_ARRAY_LENGTH)) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == UserSnapshot.class
                    || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }
}
```

Trong ví dụ:

1. Kiểm tra giới hạn tài nguyên trước.
2. Nếu có bất kỳ giới hạn nào bị vượt, trả `REJECTED` ngay.
3. Nếu không có lớp để đánh giá, trả `UNDECIDED`.
4. Chấp nhận các lớp được nêu rõ.
5. Từ chối lớp khác.

Danh sách lớp trong ví dụ chỉ là chính sách minh họa cho một object graph rất đơn giản. Ứng dụng thực tế phải xem xét toàn bộ các kiểu có thể xuất hiện trong graph, bao gồm collection, lớp phần tử, mảng và các kiểu phụ trợ mà định dạng serialization thực sự sử dụng.

Không nên thay allow-list cụ thể bằng quy tắc quá rộng như cho phép mọi lớp trong toàn bộ classpath hoặc mọi lớp của một module mà không có lý do rõ ràng.

## 6. Vì sao `UNDECIDED` có thể tạo ra chính sách fail-open?

Giả sử filter chỉ có nhiệm vụ từ chối một lớp nguy hiểm:

```java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == DangerousPayload.class) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Filter này hoạt động như một **deny-list**: lớp cụ thể bị từ chối, những lớp khác không thuộc phạm vi quyết định của filter.

Nếu mục tiêu là chỉ cho phép `UserSnapshot` và từ chối mọi lớp khác, đoạn trên chưa đủ. Những lớp không phải `DangerousPayload` vẫn nhận `UNDECIDED` và có thể được đọc.

Một allow-list nghiêm ngặt cần trả `REJECTED` cho lớp không được liệt kê:

```java
ObjectInputFilter allowList = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == UserSnapshot.class || type == String.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

Một lựa chọn khác là dùng `ObjectInputFilter.rejectUndecidedClass()` để chuyển kết quả `UNDECIDED` thành từ chối đối với các class chưa được chấp nhận.

### Khi nào nên trả `UNDECIDED`?

Trả `UNDECIDED` khi:

- Filter chỉ kiểm tra một phần chính sách.
- Lần kiểm tra không có `serialClass` và filter không có lý do để từ chối chỉ dựa trên lớp.
- Filter đang được kết hợp với filter khác chịu trách nhiệm cho các lớp hoặc giới hạn còn lại.
- Filter không muốn áp đặt quyết định cho những trường hợp ngoài phạm vi của nó.

### Khi nào không nên để `UNDECIDED` cho class không xác định?

Nếu mục tiêu là allow-list nghiêm ngặt, class không được liệt kê phải bị từ chối. Có thể trả `REJECTED` trực tiếp hoặc dùng `rejectUndecidedClass` khi cấu trúc filter được thiết kế để trả `UNDECIDED` cho class ngoài phạm vi.

## 7. Dùng `ObjectInputFilter.allowFilter()` trong Java 17

Java 17 cung cấp helper `allowFilter(Predicate<Class<?>>, Status)` để tạo filter theo predicate của lớp.

Cú pháp:

```java
ObjectInputFilter allowFilter = ObjectInputFilter.allowFilter(
        classPredicate,
        otherStatus
);
```

Hành vi:

- Nếu `serialClass()` là `null`, filter trả `UNDECIDED`.
- Nếu predicate trả `true`, filter trả `ALLOWED`.
- Nếu predicate trả `false`, filter trả trạng thái `otherStatus`.

Ví dụ allow-list:

```java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.allowFilter(
        type -> type == UserSnapshot.class
                || type == String.class,
        ObjectInputFilter.Status.REJECTED
);
```

Đối với class không nằm trong danh sách, `otherStatus` là `REJECTED`. Đây là lựa chọn phù hợp khi filter phải tự quyết định lớp được chấp nhận hay từ chối.

Nếu dùng `UNDECIDED` làm `otherStatus`:

```java
ObjectInputFilter partialAllowFilter = ObjectInputFilter.allowFilter(
        type -> type == UserSnapshot.class,
        ObjectInputFilter.Status.UNDECIDED
);
```

filter chỉ chấp nhận `UserSnapshot` và không đưa ra quyết định về các lớp khác. Nếu dùng riêng filter này, các lớp không khớp không tự động bị chặn. Hãy cân nhắc chính sách tổng thể trước khi chọn trạng thái này.

## 8. Dùng `ObjectInputFilter.rejectFilter()` để tạo deny-list

`rejectFilter(Predicate<Class<?>>, Status)` tạo filter từ predicate xác định các lớp cần từ chối.

Hành vi:

- `serialClass()` là `null`: trả `UNDECIDED`.
- Predicate đúng: trả `REJECTED`.
- Predicate sai: trả trạng thái `otherStatus`.

Ví dụ từ chối dynamic proxy:

```java
import java.io.ObjectInputFilter;
import java.lang.reflect.Proxy;

ObjectInputFilter noProxyFilter = ObjectInputFilter.rejectFilter(
        Proxy::isProxyClass,
        ObjectInputFilter.Status.UNDECIDED
);
```

Filter này từ chối các proxy class. Các lớp còn lại nhận `UNDECIDED` vì filter chỉ chịu trách nhiệm cho một quy tắc deny cụ thể.

Có thể đặt trạng thái khác cho trường hợp predicate sai:

```java
ObjectInputFilter proxyFilter = ObjectInputFilter.rejectFilter(
        Proxy::isProxyClass,
        ObjectInputFilter.Status.ALLOWED
);
```

Trong trường hợp này, mọi lớp không phải proxy được filter chấp nhận. Cần thận trọng: đây là quyết định rộng hơn nhiều so với việc chỉ từ chối proxy. Nếu ứng dụng cần allow-list, hãy dùng filter chuyên trách allow-list thay vì biến một deny-list thành chính sách chấp nhận mọi thứ còn lại.

## 9. Kết hợp filter bằng `ObjectInputFilter.merge()`

Java 17 cung cấp `ObjectInputFilter.merge(filter1, filter2)` để kết hợp hai filter.

Quy tắc kết hợp:

1. Gọi filter thứ nhất.
2. Nếu filter thứ nhất trả `REJECTED`, kết quả là `REJECTED`.
3. Nếu chưa bị từ chối, gọi filter thứ hai.
4. Nếu filter thứ hai trả `REJECTED`, kết quả là `REJECTED`.
5. Nếu một trong hai trả `ALLOWED`, kết quả là `ALLOWED`.
6. Nếu cả hai đều `UNDECIDED`, kết quả là `UNDECIDED`.

Bảng kết quả:

| Filter A | Filter B | Kết quả merge |
| --- | --- | --- |
| `REJECTED` | `ALLOWED` | `REJECTED` |
| `REJECTED` | `UNDECIDED` | `REJECTED` |
| `ALLOWED` | `REJECTED` | `REJECTED` |
| `ALLOWED` | `ALLOWED` | `ALLOWED` |
| `ALLOWED` | `UNDECIDED` | `ALLOWED` |
| `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |

**REJECTED luôn có quyền phủ quyết.** Một filter cho phép không thể ghi đè quyết định từ chối của filter còn lại.

Ví dụ kết hợp allow-list với giới hạn tài nguyên:

```java
import java.io.ObjectInputFilter;

ObjectInputFilter classFilter = ObjectInputFilter.allowFilter(
        type -> type == UserSnapshot.class
                || type == String.class,
        ObjectInputFilter.Status.REJECTED
);

ObjectInputFilter resourceFilter = info -> {
    if (info.depth() > 20
            || info.references() > 2_000
            || info.streamBytes() > 1_000_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter combined = ObjectInputFilter.merge(
        classFilter,
        resourceFilter
);
```

Kết quả:

- Lớp nằm trong allow-list và không vượt giới hạn: `ALLOWED`.
- Lớp không nằm trong allow-list: `REJECTED`.
- Bất kỳ giới hạn tài nguyên nào bị vượt: `REJECTED`.
- Lần kiểm tra không có class và không vượt giới hạn: `UNDECIDED`.

Cách tách filter theo trách nhiệm giúp code dễ hiểu: một filter quản lý lớp, một filter quản lý tài nguyên.

## 10. Dùng `rejectUndecidedClass()` để đóng chính sách allow-list

`ObjectInputFilter.rejectUndecidedClass(filter)` tạo một filter bao quanh filter ban đầu và chuyển các kết quả `UNDECIDED` thành `REJECTED` đối với class chưa được chấp nhận, với xử lý riêng cho trường hợp không có class và mảng.

Ví dụ:

```java
ObjectInputFilter partialFilter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == UserSnapshot.class || type == String.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter strictFilter =
        ObjectInputFilter.rejectUndecidedClass(partialFilter);
```

Khi dùng `strictFilter`:

- Lớp được filter chấp nhận rõ ràng vẫn là `ALLOWED`.
- Lớp không được filter quyết định sẽ bị chuyển thành `REJECTED`.
- Lần kiểm tra không có class vẫn có thể là `UNDECIDED` để filter khác đánh giá các giới hạn tài nguyên.
- Mảng được xử lý theo kiểu component cơ sở; mảng primitive có quy tắc riêng.

Điều này hữu ích khi filter ban đầu chỉ đánh dấu rõ các lớp được phép và để những lớp còn lại ở trạng thái chưa quyết định.

### Vì sao không chuyển mọi `UNDECIDED` thành `REJECTED` một cách đơn giản?

Một filter có thể được gọi khi không có class cần kiểm tra, nhưng vẫn có thông tin về depth, references và stream bytes. Nếu biến mọi `UNDECIDED` thành `REJECTED` bất kể trường hợp, có thể từ chối cả lần kiểm tra tài nguyên mà filter class-based không có ý kiến.

`rejectUndecidedClass` được thiết kế để tập trung vào quyết định đối với class và xử lý riêng trường hợp mảng/primitive, thay vì chỉ thay enum một cách máy móc.

## 11. Kết hợp allow-list, deny-list và resource filter

Một chính sách thường cần nhiều phần:

- Allow-list cho lớp ứng dụng được phép.
- Deny-list cho một số loại lớp không được chấp nhận.
- Resource filter cho depth, references, stream bytes và array length.

Ví dụ:

```java
import java.io.ObjectInputFilter;
import java.lang.reflect.Proxy;

ObjectInputFilter allowApplicationTypes =
        ObjectInputFilter.allowFilter(
                type -> type == UserSnapshot.class
                        || type == String.class,
                ObjectInputFilter.Status.UNDECIDED
        );

ObjectInputFilter rejectProxyTypes =
        ObjectInputFilter.rejectFilter(
                Proxy::isProxyClass,
                ObjectInputFilter.Status.UNDECIDED
        );

ObjectInputFilter resourceLimits = info -> {
    if (info.depth() > 20
            || info.references() > 2_000
            || info.streamBytes() > 1_000_000
            || (info.arrayLength() >= 0
                && info.arrayLength() > 100_000)) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter combined = ObjectInputFilter.merge(
        allowApplicationTypes,
        rejectProxyTypes
);

combined = ObjectInputFilter.merge(combined, resourceLimits);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(combined);
```

Trong ví dụ này:

- `allowApplicationTypes` xác nhận các kiểu ứng dụng được phép.
- `rejectProxyTypes` phủ quyết proxy class.
- `resourceLimits` từ chối object graph vượt giới hạn.
- `rejectUndecidedClass` chuyển các lớp không được chấp nhận rõ ràng thành từ chối.

Nếu filter allow-list được tạo với `otherStatus = REJECTED`, các lớp ngoài danh sách đã bị từ chối ngay; khi đó wrapper `rejectUndecidedClass` có thể không cần cho quyết định lớp thông thường. Chọn một cách thể hiện chính sách nhất quán để người đọc hiểu rõ nơi nào chịu trách nhiệm từ chối.

## 12. Gắn filter vào `ObjectInputStream`

Có thể gắn filter cho từng stream bằng `setObjectInputFilter()`. Hãy đặt filter trước khi gọi `readObject()`:

```java
import java.io.ByteArrayInputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

static Object readFiltered(byte[] bytes)
        throws Exception {

    try (ObjectInputStream input = new ObjectInputStream(
            new ByteArrayInputStream(bytes))) {

        input.setObjectInputFilter(createFilter());

        return input.readObject();
    }
}
```

Filter được áp dụng khi stream đọc object graph. Nếu một lớp bị từ chối, thao tác đọc sẽ thất bại thay vì trả object đó cho ứng dụng.

Một stream-specific filter hữu ích khi mỗi luồng dữ liệu có một tập lớp hợp lệ khác nhau. Ví dụ, stream nhập hồ sơ người dùng chỉ cần một số DTO, còn stream nhập cấu hình có thể cần các kiểu khác.

Không chờ đến sau khi đã đọc object rồi mới đặt filter. Filter cần có hiệu lực trong quá trình giải tuần tự hóa để ngăn lớp hoặc cấu trúc không được phép được khôi phục.

## 13. Ví dụ hoàn chỉnh: chỉ đọc một record được cho phép

Ví dụ sau ghi một `UserSnapshot` vào byte array, sau đó đọc lại bằng filter allow-list.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class AllowedRecordDemo {

    record UserSnapshot(String username, int level)
            implements Serializable {
    }

    static byte[] serialize(Object value) throws Exception {
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(buffer)) {

            output.writeObject(value);
            return buffer.toByteArray();
        }
    }

    static ObjectInputFilter createFilter() {
        return ObjectInputFilter.allowFilter(
                type -> type == UserSnapshot.class
                        || type == String.class,
                ObjectInputFilter.Status.REJECTED
        );
    }

    static Object deserialize(byte[] bytes) throws Exception {
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {

            input.setObjectInputFilter(createFilter());
            return input.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = serialize(new UserSnapshot("lan", 3));

        Object restored = deserialize(bytes);

        System.out.println(restored);
    }
}
```

Kết quả:

```text
UserSnapshot[username=lan, level=3]
```

Filter chấp nhận record được chỉ định. Nếu stream chứa một lớp khác không nằm trong chính sách, filter trả `REJECTED` và quá trình đọc bị chặn.

Ví dụ minh họa một object graph đơn giản. Trong ứng dụng thực tế, cần liệt kê tất cả các kiểu có thể được đọc hợp lệ; không được giả định một allow-list chỉ có record gốc sẽ đủ cho mọi cấu trúc object.

## 14. Ví dụ từ chối lớp ngoài allow-list

Có thể chứng minh việc từ chối bằng cách serialize một lớp khác rồi dùng filter chỉ cho phép `UserSnapshot`.

```java
import java.io.Serializable;

record AdminCommand(String command) implements Serializable {
}
```

Giả sử filter chỉ cho phép:

```java
ObjectInputFilter filter = ObjectInputFilter.allowFilter(
        type -> type == UserSnapshot.class
                || type == String.class,
        ObjectInputFilter.Status.REJECTED
);
```

Nếu stream chứa `AdminCommand`, predicate trả `false` cho lớp đó. `otherStatus` là `REJECTED`, nên filter từ chối.

Có thể xử lý lỗi ở ranh giới đọc:

```java
try (ObjectInputStream input = new ObjectInputStream(
        new ByteArrayInputStream(bytes))) {

    input.setObjectInputFilter(filter);

    Object value = input.readObject();
    System.out.println(value);

} catch (java.io.InvalidClassException ex) {
    System.err.println("Object bị filter từ chối: " + ex.getMessage());
}
```

Không nên bắt lỗi rồi bỏ qua và tiếp tục xử lý object chưa được đọc thành công. Hãy ghi nhận sự kiện từ chối và trả lỗi phù hợp cho tầng gọi.

## 15. Dùng pattern filter từ `ObjectInputFilter.Config.createFilter()`

Ngoài custom filter bằng lambda, Java hỗ trợ tạo filter từ chuỗi pattern:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=2000;maxbytes=1000000;"
                + "maxarray=100000;"
                + "com.example.dto.**;!*"
);
```

Các thành phần:

| Pattern | Ý nghĩa |
| --- | --- |
| `maxdepth=20` | Giới hạn độ sâu object graph. |
| `maxrefs=2000` | Giới hạn số lượng references. |
| `maxbytes=1000000` | Giới hạn số byte đọc từ stream. |
| `maxarray=100000` | Giới hạn độ dài mảng. |
| `com.example.dto.**` | Cho phép lớp trong package và các subpackage tương ứng. |
| `!*` | Từ chối lớp còn lại nếu không khớp pattern cho phép trước đó. |

Với pattern class, các pattern được xét từ trái sang phải; pattern đầu tiên khớp quyết định trạng thái cho lớp. Các giới hạn tài nguyên được kiểm tra và có thể trả `REJECTED` nếu vượt ngưỡng.

Phân biệt wildcard:

- `com.example.dto.*` khớp lớp trực tiếp trong package đó.
- `com.example.dto.**` khớp lớp trong package và các subpackage.
- `!com.example.dto.Internal` từ chối lớp cụ thể.
- `!*` từ chối các lớp còn lại nếu không có pattern trước đó chấp nhận.

Pattern filter trả `UNDECIDED` nếu không có pattern class nào khớp và không có giới hạn nào bị vượt. Nếu muốn chính sách allow-list nghiêm ngặt, một pattern từ chối cuối như `!*` giúp quyết định rõ cho lớp còn lại.

Tên package và module trong pattern phải phù hợp với class thực tế. Không nên thêm một wildcard rộng chỉ để làm test chạy qua mà không hiểu những lớp nào sẽ được chấp nhận.

## 16. Gắn filter toàn JVM

Với ứng dụng cần một chính sách chung, có thể cấu hình filter toàn JVM bằng system property:

```bash
java -Djdk.serialFilter="maxdepth=20;maxrefs=2000;maxbytes=1000000;com.example.dto.**;!*" -m com.example.app/com.example.Main
```

Hoặc cấu hình qua API:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=2000;maxbytes=1000000;"
                + "com.example.dto.**;!*"
);

ObjectInputFilter.Config.setSerialFilter(filter);
```

Filter toàn JVM áp dụng ở phạm vi ứng dụng Java process và cần được thiết lập theo vòng đời khởi động. Nếu đã cấu hình filter toàn cục ở nơi khác, việc đặt lại có thể bị từ chối. Nên quản lý cấu hình ở một điểm khởi tạo rõ ràng.

Global filter hữu ích khi muốn có chính sách nền cho toàn ứng dụng. Với các luồng có ngữ cảnh khác nhau, có thể cần filter riêng cho từng stream hoặc filter factory.

## 17. Filter factory và ngữ cảnh trong Java 17

Java 17 bổ sung cơ chế filter factory theo JEP 415 để ứng dụng chọn hoặc kết hợp filter dựa trên ngữ cảnh tạo `ObjectInputStream`.

`ObjectInputFilter.Config.setSerialFilterFactory(...)` nhận một `BinaryOperator<ObjectInputFilter>` để quyết định filter mới từ filter hiện tại và filter được yêu cầu.

Ví dụ về mặt cấu hình:

```java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

BinaryOperator<ObjectInputFilter> factory =
        (currentFilter, requestedFilter) -> {
            if (currentFilter == null) {
                return requestedFilter;
            }

            return ObjectInputFilter.merge(
                    currentFilter,
                    requestedFilter
            );
        };

ObjectInputFilter.Config.setSerialFilterFactory(factory);
```

Đây là ví dụ khái niệm về việc kết hợp filter. Chính sách thực tế cần xét trường hợp cả hai filter là `null`, filter toàn cục, filter theo thread/context và cách ứng dụng muốn xử lý `UNDECIDED`.

Filter factory được gọi khi filter của stream được thiết lập hoặc cập nhật theo cơ chế của `ObjectInputStream`. Nó cho phép ứng dụng đưa chính sách context-specific vào quá trình deserialization, ví dụ:

- Luồng nhập dữ liệu từ dịch vụ A chỉ được phép các kiểu A.
- Luồng nhập dữ liệu từ tệp cấu hình chỉ được phép các kiểu cấu hình.
- Luồng do một module/framework tạo ra có thể cần một filter riêng.
- Một filter toàn cục luôn áp dụng giới hạn tài nguyên, còn filter riêng quyết định lớp theo ngữ cảnh.

Không nên cài factory tùy tiện trong một thư viện dùng chung vì đây là cấu hình ảnh hưởng đến quá trình deserialization của ứng dụng. Nên để ứng dụng chủ quản chính sách và cấu hình factory tại một điểm khởi tạo duy nhất.

## 18. Những lỗi thường gặp khi dùng ba trạng thái

| Lỗi | Vì sao có vấn đề | Cách xử lý |
| --- | --- | --- |
| Trả `UNDECIDED` cho mọi lớp ngoài danh sách | Lớp ngoài danh sách có thể vẫn được đọc nếu không có filter khác từ chối. | Trả `REJECTED` hoặc dùng `rejectUndecidedClass`. |
| Nghĩ `ALLOWED` ghi đè mọi filter khác | Trong `merge`, một kết quả `REJECTED` vẫn phủ quyết. | Xem chính sách kết hợp; `REJECTED` có ưu tiên từ chối. |
| Trả `REJECTED` khi `serialClass()` là null mà không kiểm tra resource | Filter class-based có thể từ chối nhầm lần kiểm tra chỉ chứa metrics. | Kiểm tra depth/references/bytes trước; sau đó trả `UNDECIDED` nếu không có class. |
| Không giới hạn array length | Mảng lớn có thể gây tiêu thụ bộ nhớ đáng kể. | Kiểm tra `arrayLength()`. |
| Chỉ kiểm tra class, bỏ qua graph limits | Một lớp hợp lệ vẫn có thể xuất hiện trong graph quá sâu hoặc quá lớn. | Kết hợp allow-list với resource filter. |
| Dùng deny-list nhỏ như allow-list | Những lớp không khớp deny-list vẫn có thể nhận `UNDECIDED`. | Viết allow-list rõ ràng và từ chối lớp ngoài danh sách. |
| Trả `null` từ `checkInput()` | Vi phạm hợp đồng API và có thể gây lỗi không dự đoán. | Luôn trả một trong ba trạng thái. |
| Đặt filter sau `readObject()` | Object graph đã được giải tuần tự hóa trước khi filter có hiệu lực. | Gắn filter trước khi đọc object. |
| Cho phép cả package quá rộng | Nhiều lớp ngoài nhu cầu có thể được đọc. | Giới hạn theo lớp/package cụ thể và kiểm tra object graph hợp lệ. |
| Xem filter là validation nghiệp vụ | Filter kiểm soát class và resource, không xác nhận dữ liệu có ý nghĩa nghiệp vụ. | Kiểm tra dữ liệu sau khi đọc bằng validator của ứng dụng. |

## 19. Filter không thay thế validation và xác thực

Một object có thể thuộc lớp được phép nhưng chứa giá trị không hợp lệ:

```java
record UserSnapshot(String username, int level)
        implements java.io.Serializable {
}
```

Ví dụ stream chứa:

```java
new UserSnapshot("", -100)
```

Filter có thể chấp nhận `UserSnapshot` vì lớp đó nằm trong allow-list. Tuy nhiên, điều đó không chứng minh:

- `username` không rỗng.
- `level` nằm trong khoảng hợp lệ.
- Người gửi có quyền tạo hoặc cập nhật user đó.
- Dữ liệu thuộc đúng tenant hoặc đúng người dùng.
- Object không chứa thông tin giả mạo.

Sau khi đọc object, ứng dụng vẫn phải validate dữ liệu và kiểm tra quyền nghiệp vụ:

```java
static void validate(UserSnapshot user) {
    if (user.username() == null || user.username().isBlank()) {
        throw new IllegalArgumentException("username không hợp lệ");
    }

    if (user.level() < 0 || user.level() > 10) {
        throw new IllegalArgumentException("level ngoài phạm vi");
    }
}
```

Filter quyết định **có cho phép Java tái tạo kiểu/object graph này không**. Validation quyết định **dữ liệu sau khi đọc có hợp lệ với ứng dụng không**. Authorization quyết định **người gửi có được phép thực hiện hành động tương ứng không**.

Ba lớp kiểm soát có vai trò khác nhau và không thay thế lẫn nhau.

## 20. Khi nào nên tránh Java Object Deserialization?

Serialization Filtering giúp giảm rủi ro khi ứng dụng phải đọc Java serialized data, nhưng không biến dữ liệu không đáng tin cậy thành an toàn tuyệt đối.

Nếu thiết kế hệ thống mới, hãy cân nhắc định dạng dữ liệu chỉ mang dữ liệu như JSON, Protocol Buffers hoặc một schema rõ ràng, cùng parser có giới hạn kích thước và validation phù hợp. Những định dạng này vẫn cần kiểm tra đầu vào, nhưng không tự động khôi phục tùy ý object graph Java theo cơ chế native serialization.

Nếu phải tiếp tục dùng Java Object Serialization:

- Không đọc serialized data không đáng tin cậy mà không có filter phù hợp.
- Dùng allow-list theo use case.
- Đặt giới hạn depth, references, bytes và array length.
- Từ chối các lớp không được dự kiến.
- Validate dữ liệu sau khi đọc.
- Không coi filter là cơ chế xác thực người gửi.
- Quản lý filter toàn cục và filter theo stream/context ở một nơi rõ ràng.

Các API `ObjectInputFilter` và filter factory vẫn là cơ chế hiện hành của JDK 17. Tránh dựa vào các mẹo cũ như tắt kiểm tra module hoặc thay đổi cơ chế bảo mật toàn JVM để cho phép mọi object đọc được.

## 21. Bài thực hành

### Bài 1 — phân biệt ba trạng thái

Viết một filter nhận `FilterInfo`:

- Trả `ALLOWED` cho `UserSnapshot.class`.
- Trả `REJECTED` cho `AdminCommand.class`.
- Trả `UNDECIDED` cho các lớp khác.

Giải thích điều gì xảy ra nếu filter này được dùng một mình và stream chứa một lớp thứ ba.

### Bài 2 — giới hạn tài nguyên

Viết filter từ chối nếu:

- `depth()` lớn hơn 10.
- `references()` lớn hơn 1.000.
- `streamBytes()` lớn hơn 500.000.
- `arrayLength()` lớn hơn 50.000.

Nếu không vi phạm giới hạn, trả `UNDECIDED` để filter khác quyết định lớp.

### Bài 3 — dùng allowFilter

Tạo `allowFilter` chỉ chấp nhận `UserSnapshot.class` và `String.class`, dùng `REJECTED` làm trạng thái còn lại. Thử giải tuần tự hóa một object thuộc lớp khác và quan sát lỗi.

### Bài 4 — dùng rejectFilter

Tạo filter từ chối proxy class bằng `Proxy.isProxyClass`, các lớp khác trả `UNDECIDED`. Giải thích vì sao filter này chưa phải allow-list.

### Bài 5 — kết hợp filter

Tạo một class filter và một resource filter, sau đó kết hợp bằng `ObjectInputFilter.merge()`. Kiểm tra bảng kết quả khi một filter cho phép nhưng filter còn lại từ chối.

### Bài 6 — strict allow-list

Tạo filter chỉ trả `ALLOWED` cho một lớp được chỉ định và `UNDECIDED` cho lớp khác. Bọc bằng `rejectUndecidedClass()`. So sánh hành vi với filter chưa được bọc.

### Bài 7 — pattern filter

Tạo filter bằng `Config.createFilter()` với giới hạn depth, references, bytes và package pattern. Thêm pattern từ chối cuối cùng để lớp không khớp bị chặn. Thử một lớp trong package được phép và một lớp ngoài package.

### Bài 8 — filter trước khi đọc

Serialize một record, sau đó tạo `ObjectInputStream`, gọi `setObjectInputFilter()` trước `readObject()` và đọc lại. Thử thay filter bằng một chính sách từ chối record để quan sát hành vi.

## 22. Ghi nhớ nhanh

| Nhu cầu | Cách làm |
| --- | --- |
| Chấp nhận lần kiểm tra | Trả `ObjectInputFilter.Status.ALLOWED`. |
| Từ chối lần kiểm tra | Trả `ObjectInputFilter.Status.REJECTED`. |
| Filter không có ý kiến | Trả `ObjectInputFilter.Status.UNDECIDED`. |
| Đọc lớp đang được kiểm tra | `info.serialClass()`. |
| Giới hạn độ sâu | Kiểm tra `info.depth()`. |
| Giới hạn số reference | Kiểm tra `info.references()`. |
| Giới hạn số byte | Kiểm tra `info.streamBytes()`. |
| Giới hạn độ dài mảng | Kiểm tra `info.arrayLength()`. |
| Tạo filter allow-list theo predicate | `ObjectInputFilter.allowFilter(...)`. |
| Tạo filter deny-list theo predicate | `ObjectInputFilter.rejectFilter(...)`. |
| Kết hợp hai filter | `ObjectInputFilter.merge(filter1, filter2)`. |
| Từ chối class còn undecided | `ObjectInputFilter.rejectUndecidedClass(filter)`. |
| Tạo filter từ pattern | `ObjectInputFilter.Config.createFilter(pattern)`. |
| Gắn filter cho stream | `objectInputStream.setObjectInputFilter(filter)`. |
| Cấu hình filter toàn JVM | `ObjectInputFilter.Config.setSerialFilter(filter)` hoặc system property `jdk.serialFilter`. |
| Chọn filter theo ngữ cảnh | Filter factory trong Java 17. |

**Nguyên tắc cốt lõi:** `ALLOWED` là quyết định chấp nhận, `REJECTED` là quyết định từ chối, còn `UNDECIDED` chỉ có nghĩa filter hiện tại chưa đưa ra quyết định. Khi xây dựng allow-list, đừng để lớp không xác định rơi vào `UNDECIDED` mà không có cơ chế từ chối tiếp theo. Kết hợp kiểm tra lớp với giới hạn tài nguyên, gắn filter trước khi đọc object và tiếp tục validate dữ liệu sau khi giải tuần tự hóa.
