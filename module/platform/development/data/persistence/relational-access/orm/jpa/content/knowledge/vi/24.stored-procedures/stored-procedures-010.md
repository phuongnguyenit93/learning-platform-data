# Đánh giá giới hạn tính khả chuyển của lời gọi thủ tục trong JPA

**Stored procedure** (thủ tục lưu trữ) là cách đưa một phần logic xử lý dữ liệu xuống hệ quản trị cơ sở dữ liệu (DBMS). Trong ứng dụng JPA, thủ tục thường được gọi bằng `StoredProcedureQuery`, được khai báo bằng `@NamedStoredProcedureQuery` hoặc được tích hợp qua JDBC khi cần những khả năng đặc thù. Điểm dễ gây hiểu nhầm là:

> **JPA có API chuẩn để gọi stored procedure, nhưng điều đó không có nghĩa một thủ tục, chữ ký tham số và hành vi trả kết quả sẽ chạy nguyên vẹn trên mọi DBMS, JDBC driver hoặc JPA provider.**

Ví dụ một ứng dụng quản lý kho có thủ tục `reserve_stock` với đầu vào là sản phẩm và số lượng cần giữ. Ứng dụng có thể dùng một đoạn Java giống nhau để gọi thủ tục trên hai môi trường. Tuy nhiên, **phần SQL tạo thủ tục**, **cách đăng ký tham số OUT**, **kiểu dữ liệu**, **giao dịch**, **cách trả result set** và **mã lỗi khi hết hàng** có thể khác nhau.

“Khả chuyển” vì vậy phải được đánh giá ở nhiều mức:

1. **Khả chuyển của mã Java/JPA:** mã biên dịch bằng các API chuẩn hay dùng extension của Hibernate/EclipseLink?
2. **Khả chuyển của lời gọi qua provider và driver:** tên/vị trí tham số, kiểu SQL, cursor, thứ tự result sets có được hỗ trợ nhất quán không?
3. **Khả chuyển của chính stored procedure:** cú pháp SQL/PL/SQL/T-SQL/PLpgSQL, transaction và tính năng DBMS có thể chuyển sang hệ quản trị khác không?
4. **Khả chuyển của hợp đồng nghiệp vụ:** khi đổi database, kết quả và tác dụng dữ liệu có giữ nguyên nghĩa không?

Bài học trình bày phương pháp đánh giá từng tầng, API chuẩn của JPA, những chỗ phụ thuộc DBMS, ví dụ Java có transaction, mẫu thiết kế adapter, ma trận rủi ro, chiến lược giảm phụ thuộc và cách xây bộ integration tests cho một chức năng gọi thủ tục thực tế.

---

## 1. “Khả chuyển” có nhiều cấp độ

Giả sử hệ thống `InventoryService` cần giữ trước 5 sản phẩm trong kho. Một thủ tục dự kiến làm việc sau:

```text
reserve_stock(productId = 101, requestedQuantity = 5)
    |
    +-- Xác thực sản phẩm tồn tại
    +-- Kiểm tra số lượng có thể giữ
    +-- Cập nhật lượng tồn khả dụng
    +-- Ghi lịch sử giữ hàng
    +-- Trả trạng thái, số lượng còn lại
```

Từ Java, ta muốn gọi:

```java
StoredProcedureQuery query =
    em.createStoredProcedureQuery("reserve_stock");
```

Nhưng tồn tại các mức khả chuyển khác nhau:

| Mức | Câu hỏi thực tế | Ví dụ vấn đề |
| --- | --- | --- |
| **Mã nguồn** | Có cần sửa import/API Java khi đổi provider? | `StoredProcedureQuery` là chuẩn; API native `Session.doWork(...)` thì không. |
| **Cấu hình mapping** | Provider có hiểu và thực thi giống nhau không? | Named parameter, `REF_CURSOR`, result set mapping. |
| **SQL/thủ tục** | Thủ tục SQL có chạy trên DBMS mới không? | `CREATE PROCEDURE` và ngôn ngữ thân thủ tục khác nhau. |
| **Kiểu dữ liệu** | IN/OUT parameters có chuyển đúng kiểu không? | `BIGINT`, `NUMERIC`, `UUID`, `TIMESTAMP WITH TIME ZONE`. |
| **Kết quả** | Cùng lời gọi có nhận cùng loại/chuỗi kết quả không? | Result sets, update counts, cursor, OUT parameters. |
| **Transaction** | Khi rollback, tác dụng dữ liệu có được hoàn nguyên đúng không? | Procedure tự quản lý transaction hoặc dùng connection khác. |
| **Lỗi** | Lỗi nghiệp vụ được nhận diện giống nhau không? | Vendor error code, `SQLSTATE` và exception wrapping. |
| **Vận hành** | Có thể cài đặt, nâng phiên bản và cấp quyền như nhau không? | Schema/package, execute privilege, migration. |

Điều quan trọng là **không đánh giá tất cả các mục bằng một nhãn duy nhất “portable” hoặc “non-portable”**. Một implementation có thể dùng **API Java chuẩn** nhưng vẫn phụ thuộc hoàn toàn vào **T-SQL của SQL Server**.

### 1.1. Ba khái niệm cần phân biệt

**Tính khả chuyển của API (*API portability*)**

Ứng dụng chỉ gọi những giao diện Jakarta Persistence tiêu chuẩn, chẳng hạn:

```java
em.createStoredProcedureQuery(...);
procedure.registerStoredProcedureParameter(...);
procedure.setParameter(...);
procedure.execute();
procedure.getOutputParameterValue(...);
```

Ưu điểm là không phụ thuộc trực tiếp vào tên class nội bộ của một provider.

**Tính khả chuyển của lược đồ và SQL (*database portability*)**

Thân thủ tục phải hoạt động trên hệ quản trị đích. Đây là vấn đề khác hoàn toàn với việc Java dùng `StoredProcedureQuery`.

**Tính khả chuyển của hành vi (*behavioral portability*)**

Kết quả trả về, lỗi, transaction và đồng thời phải giữ cùng ngữ nghĩa khi đổi nền tảng. Đây thường là mức khó nhất: code Java có thể biên dịch và thủ tục có thể được viết lại, nhưng kết quả vẫn sai nếu đổi cách khóa dữ liệu hoặc cách tính affected rows.

## 2. Chuỗi phụ thuộc khi JPA gọi stored procedure

Một lời gọi JPA đi qua nhiều lớp:

```text
+----------------------------------------------+
| Ứng dụng Java / Domain / Service              |
|  - Giao dịch nghiệp vụ                        |
|  - Kiểm tra quyền / dữ liệu                   |
|  - Gọi cổng reserveStock(...)                 |
+---------------------+------------------------+
                      |
                      v
+----------------------------------------------+
| Jakarta Persistence API                       |
|  EntityManager / StoredProcedureQuery         |
|  @NamedStoredProcedureQuery / ParameterMode   |
+---------------------+------------------------+
                      |
                      v
+----------------------------------------------+
| JPA provider                                  |
|  Hibernate ORM, EclipseLink, ...              |
|  Dịch lời gọi, bind, mapping, dialect          |
+---------------------+------------------------+
                      |
                      v
+----------------------------------------------+
| JDBC driver                                  |
|  CallableStatement, JDBC types, cursors       |
|  ResultSet, update counts, OUT parameters     |
+---------------------+------------------------+
                      |
                      v
+----------------------------------------------+
| DBMS                                         |
|  PostgreSQL / Oracle / SQL Server / MySQL ... |
|  Stored procedure, transaction, SQL dialect  |
+----------------------------------------------+
```

Thay một lớp có thể thay đổi hành vi:

- **Đổi JPA provider:** cách ánh xạ parameters, hỗ trợ cursor/result sets hoặc SQL call syntax có thể khác.
- **Giữ provider, đổi JDBC driver:** hỗ trợ OUT parameters hoặc kiểu timestamp có thể khác.
- **Giữ Java, đổi DBMS:** thân thủ tục chắc chắn cần kiểm tra lại, thường phải viết lại nếu dùng ngôn ngữ thủ tục riêng.
- **Đổi DBMS version:** SQL syntax, quyền, implicit conversions và transaction restrictions có thể thay đổi.

Vì vậy, khi phát biểu “chức năng gọi thủ tục portable”, phải nêu rõ **portable giữa những phiên bản nào của những lớp nào**.

## 3. JPA tiêu chuẩn hóa những gì?

Jakarta Persistence cung cấp các thành phần chung cho lời gọi stored procedure.

### 3.1. Tạo lời gọi

```java
StoredProcedureQuery procedure =
    em.createStoredProcedureQuery("reserve_stock");
```

Tên `reserve_stock` biểu diễn routine mà provider sẽ gọi. API này là chuẩn JPA, nhưng **tên routine, schema/package và cách phân giải tên** vẫn là vấn đề database/provider.

### 3.2. Đăng ký tham số

```java
procedure.registerStoredProcedureParameter(
    1,
    Long.class,
    ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    2,
    Integer.class,
    ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    3,
    Integer.class,
    ParameterMode.OUT
);
```

JPA cung cấp các chế độ `IN`, `OUT`, `INOUT` và `REF_CURSOR`. Điều này không có nghĩa mọi kiểu SQL và mọi dạng cursor đều được mọi driver hỗ trợ như nhau.

### 3.3. Bind và thực thi

```java
procedure.setParameter(1, 101L);
procedure.setParameter(2, 5);

boolean firstIsResultSet = procedure.execute();
```

`execute()` trả Boolean theo **loại kết quả đầu tiên**, không phải “thành công/thất bại” của nghiệp vụ.

### 3.4. Đọc kết quả

```java
if (firstIsResultSet) {
    List<?> rows = procedure.getResultList();
} else {
    int count = procedure.getUpdateCount();
}
```

Khi có nhiều phần kết quả, `hasMoreResults()` cho phép chuyển tới phần kế tiếp. OUT parameters đọc bằng `getOutputParameterValue(...)`.

### 3.5. Metadata đặt trên entity

```java
@NamedStoredProcedureQuery(
    name = "Inventory.reserveStock",
    procedureName = "reserve_stock",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            type = Integer.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            type = Integer.class
        )
    }
)
```

Annotation trên phải được đặt ở vị trí JPA cho phép, thường trên entity managed. Nó chuẩn hóa cách **khai báo lời gọi trong Java**, chứ không chuẩn hóa nội dung thân `reserve_stock` trong DBMS.

### 3.6. Ánh xạ dữ liệu trả về

JPA có các overload:

```java
em.createStoredProcedureQuery(
    "find_recent_orders",
    OrderEntity.class
);
```

hoặc:

```java
em.createStoredProcedureQuery(
    "find_recent_orders",
    "OrderSummaryMapping"
);
```

Với `@SqlResultSetMapping` đã khai báo đúng, provider có thể ánh xạ rows thành entity, scalar hoặc constructor result. Tuy vậy, nhiều result sets có cấu trúc khác nhau là một bài toán khác với một result set duy nhất.

## 4. JPA không chuẩn hóa những gì?

Sự tồn tại của `StoredProcedureQuery` **không chuẩn hóa** những chi tiết sau:

| Hạng mục | Vì sao không thể giả định giống nhau? |
| --- | --- |
| Cú pháp `CREATE PROCEDURE` | Mỗi DBMS có ngôn ngữ và cú pháp thủ tục riêng. |
| Cú pháp gọi routine bên dưới | `CALL`, `EXEC`, block PL/SQL, function call có quy tắc khác nhau. |
| Procedure so với function | Một routine trả bảng/giá trị có thể là function trên DBMS này, nhưng là procedure với result set trên DBMS khác. |
| Named parameter binding thực tế | Driver/provider có thể cần thông tin metadata, tên và quoting đặc thù. |
| OUT/INOUT value conversion | Kiểu SQL và wrapper Java được hỗ trợ có thể khác. |
| `REF_CURSOR` | Phụ thuộc DBMS, driver và provider. |
| Nhiều result sets | Cách phát sinh và đọc có thể rất khác nhau. |
| Update counts | Chính sách của DBMS, trigger và driver ảnh hưởng. |
| Array, JSON, XML, UUID, record/composite types | Không có một cách ánh xạ stored procedure parameter giống nhau cho mọi hệ. |
| Quản lý transaction trong thân thủ tục | DBMS có quy tắc riêng cho COMMIT, ROLLBACK, savepoints, implicit commits. |
| Isolation, locking, deadlock | Cơ chế và thông báo lỗi khác nhau. |
| Vendor SQLSTATE/error code | Không nên dùng một con số vendor làm hợp đồng xuyên hệ quản trị. |
| Quyền thực thi và search path | Schema, package, user ownership, definer/invoker context khác nhau. |
| Mức tối ưu, cache plan, timeout | Provider/driver/database có đặc tính riêng. |

### 4.1. Kết luận quan trọng

**Một lời gọi JPA hợp lệ về mặt cú pháp không bảo đảm routine tồn tại hoặc vận hành giống nhau trên cơ sở dữ liệu mới.**

Đây là giới hạn nền tảng mà người thiết kế hệ thống cần chấp nhận trước khi lựa chọn stored procedure cho logic nghiệp vụ quan trọng.

## 5. Đối chiếu một số DBMS thường gặp

Các hệ quản trị phổ biến đều có cơ chế procedure/routine, nhưng khác nhau đáng kể.

| DBMS | Hệ ngôn ngữ/procedure nổi bật | Điểm cần kiểm tra khi gọi qua JPA |
| --- | --- | --- |
| **PostgreSQL** | PL/pgSQL; `CREATE FUNCTION` và `CREATE PROCEDURE` | Phân biệt function trả hàng với procedure; `CALL`, OUT arguments, refcursor, transaction restriction tùy bản phát hành/driver. |
| **Oracle Database** | PL/SQL; procedures, functions, packages | Package-qualified names, REF CURSOR, Oracle types, OUT và cursor registration. |
| **Microsoft SQL Server** | T-SQL; `CREATE PROCEDURE` và `EXEC` | Nhiều result sets, row count messages, `SET NOCOUNT`, output parameters, driver behavior. |
| **MySQL** | Stored routines; `CREATE PROCEDURE` và `CALL` | IN/OUT/INOUT, result sets và driver handling, delimiter dùng khi triển khai script. |

Bảng này giúp **đặt câu hỏi kiểm thử**, không phải cam kết tính năng hoặc hạn chế cố định cho mọi phiên bản sản phẩm.

### 5.1. PostgreSQL: procedure khác function

PostgreSQL có function có thể được dùng trong truy vấn:

```sql
SELECT * FROM find_recent_orders(101);
```

và procedure được gọi theo cú pháp:

```sql
CALL reserve_stock(101, 5, NULL);
```

Ví dụ trên **chỉ minh họa sự khác nhau giữa lệnh gọi function/procedure**, không phải signature chạy được của một function/procedure đã định nghĩa. Số lượng đối số, OUT parameters và yêu cầu client/provider có thể thay đổi theo PostgreSQL version.

Nếu một routine PostgreSQL trả tập hàng qua `RETURNS TABLE`, việc truy vấn bằng `SELECT * FROM function(...)` có thể phù hợp hơn một `StoredProcedureQuery` của JPA. Đừng giả định JPA gọi function trả bảng được như procedure không khác biệt.

### 5.2. Oracle: PL/SQL và package

Một API có thể nằm trong package:

```text
INVENTORY_API.RESERVE_STOCK
```

Lời gọi có thể liên quan đến package/owner và tham số `REF CURSOR`. Cú pháp khai báo và cách driver đưa cursor về Java khác với một procedure SQL Server trả hai `SELECT`.

Nếu chỉ test một routine không OUT/cursor, đừng kết luận toàn bộ các routines trong Oracle đều portable.

### 5.3. SQL Server: output và multiple result sets

T-SQL thường gọi procedure bằng `EXEC`:

```sql
EXEC dbo.usp_reserve_stock
    @ProductId = 101,
    @Quantity = 5,
    @StatusCode = @outputCode OUTPUT;
```

Đây là mô tả ý tưởng; biến `@outputCode` cần được khai báo trong một batch T-SQL thực sự. Java/JPA không cần xây lại chuỗi `EXEC` bằng cách nối input khi `StoredProcedureQuery` đã hỗ trợ parameter binding phù hợp.

SQL Server có thể trả **nhiều result sets** từ nhiều câu `SELECT`. Các thông điệp update count và `SET NOCOUNT` ảnh hưởng việc ứng dụng quan sát các phần kết quả.

### 5.4. MySQL: CALL và script delimiter

MySQL dùng `CALL` cho procedure, ví dụ:

```sql
CALL reserve_stock(101, 5, @status_code);
```

Việc tạo một routine thường sử dụng `DELIMITER` trong **client script** khi thân procedure có nhiều câu SQL. `DELIMITER` là chỉ thị của client công cụ SQL, không phải một câu lệnh SQL portable để gửi nguyên văn qua JDBC.

Do đó migration file của hai DBMS cũng có thể phải được quản lý riêng, dù code Java gọi một abstraction giống nhau.

## 6. Ví dụ nghiệp vụ: reserve_stock với hợp đồng tối giản

Để đánh giá khả chuyển một cách thực tế, trước tiên cần viết ra **hợp đồng nghiệp vụ độc lập với SQL dialect**.

### 6.1. Dữ liệu

Giả sử hệ thống có:

```sql
-- DDL minh họa, không cam kết chạy nguyên văn trên mọi DBMS.
CREATE TABLE inventory_balance (
    product_id BIGINT PRIMARY KEY,
    available_quantity INTEGER NOT NULL,
    reserved_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL
);
```

Một sản phẩm có:

```text
product_id = 101
available_quantity = 12
reserved_quantity = 4
```

Gọi giữ thêm 5 đơn vị thành công thì:

```text
available_quantity = 7
reserved_quantity = 9
```

Nếu yêu cầu giữ 20 đơn vị, procedure phải từ chối và không làm sai invariant dữ liệu.

### 6.2. Định nghĩa hợp đồng độc lập DBMS

```text
Routine:
    reserve_stock

Inputs:
    productId       BIGINT
    requestedAmount INTEGER

Output:
    statusCode      INTEGER

Meaning:
    0 = RESERVED
    1 = PRODUCT_NOT_FOUND
    2 = INSUFFICIENT_STOCK
    3 = INVALID_QUANTITY

Atomicity:
    Khi thất bại nghiệp vụ, inventory không thay đổi.
    Khi thành công, available giảm và reserved tăng cùng transaction.

Concurrency:
    Hai transaction đồng thời không được tạo availableQuantity âm.

Side effects:
    Không tự phát HTTP/email trực tiếp từ routine.
```

Đây là **hợp đồng ứng dụng tự đặt ra**. Những status codes không phải chuẩn JPA/SQL; ưu điểm của chúng là có thể được tái hiện khi viết routine khác nhau cho từng DBMS.

### 6.3. Mức độ khả chuyển của hợp đồng

| Thành phần | Khả chuyển tương đối | Lý do |
| --- | --- | --- |
| Hai IN tham số dạng `Long` và `Integer` | Tương đối cao | Các kiểu số cơ bản được hỗ trợ rộng rãi, nhưng vẫn cần xác nhận chuyển kiểu. |
| Một OUT `Integer` | Trung bình | Driver/provider phải hỗ trợ registration và retrieval đúng. |
| Status codes 0/1/2/3 | Cao ở mức domain | Do ứng dụng tự định nghĩa; mỗi thủ tục phải tuân thủ. |
| UPDATE số lượng atomically | Trung bình | Nhiều DBMS làm được nhưng cách locking/condition cần kiểm chứng. |
| Thân thủ tục viết một lần chạy mọi DBMS | Thấp | Ngôn ngữ và SQL dialect khác nhau. |
| Transaction được ứng dụng điều phối | Có thể giữ hợp đồng chung | Cần tránh database-specific transaction control trong procedure. |

**Thiết kế hợp đồng nhỏ với kiểu dữ liệu phổ thông giúp giảm chi phí chuyển đổi**, nhưng không biến phần định nghĩa thủ tục thành portable SQL.

## 7. Gọi hợp đồng tối giản bằng StoredProcedureQuery

Giả sử mỗi DBMS đã được cài đúng routine tương ứng có ba tham số theo vị trí:

```text
1. productId       IN  BIGINT
2. requestedAmount IN  INTEGER
3. statusCode      OUT INTEGER
```

Java sử dụng Jakarta Persistence:

```java
package com.example.inventory;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

public final class InventoryProcedureCaller {

    public int reserveStock(
            EntityManager em,
            long productId,
            int requestedAmount) {

        StoredProcedureQuery sp =
            em.createStoredProcedureQuery("reserve_stock");

        sp.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN
        );
        sp.registerStoredProcedureParameter(
            2, Integer.class, ParameterMode.IN
        );
        sp.registerStoredProcedureParameter(
            3, Integer.class, ParameterMode.OUT
        );

        sp.setParameter(1, productId);
        sp.setParameter(2, requestedAmount);

        boolean resultSet = sp.execute();

        // Duyệt các result sets/update counts nếu driver
        // phơi bày chúng trước khi lấy OUT parameter.
        while (true) {
            if (resultSet) {
                sp.getResultList();
            } else {
                int count = sp.getUpdateCount();
                if (count == -1) {
                    break;
                }
            }

            resultSet = sp.hasMoreResults();
        }

        Object value = sp.getOutputParameterValue(3);

        if (!(value instanceof Number number)) {
            throw new IllegalStateException(
                "reserve_stock returned invalid status"
            );
        }

        return number.intValue();
    }
}
```

Đoạn code không dùng Hibernate-specific API. Tuy nhiên, nó **chỉ portable nếu** provider/driver/DBMS tương ứng thực sự hỗ trợ chữ ký và cách trả OUT này.

### 7.1. Vì sao chọn positional registration?

```java
sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
```

thường giúp hợp đồng lời gọi độc lập với **tên tham số SQL** giữa các dialect — một nơi có thể gọi `p_product_id`, nơi khác `@ProductId`. Nhưng nó tạo một phụ thuộc khác: **thứ tự tham số** phải được giữ đúng khi tạo routine trên mỗi DBMS.

Positional registration không phải phép màu bảo đảm mọi driver chạy đúng; nó chỉ giảm một loại phụ thuộc khi hợp đồng nhỏ và thứ tự được quản lý chặt.

### 7.2. Vì sao vẫn duyệt kết quả dù contract chỉ cần OUT?

Có provider/driver yêu cầu xử lý các phần kết quả do stored procedure phát ra trước khi đọc OUT parameter. Nếu routine chỉ trả OUT và không phát result set/update count, vòng lặp nhanh chóng kết thúc.

Thiết kế portable hơn là **đọc/tiêu thụ các kết quả theo thứ tự**, thay vì giả định không có phần nào khác hoặc OUT luôn đọc được ngay sau `execute()`.

Trong dự án cần độ chắc chắn cao, routine có thể được thiết kế để **không phát result sets ngoài hợp đồng** và cấu hình suppress row-count messages phù hợp với DBMS. Dù vậy, phải kiểm chứng hành vi của đúng driver/provider.

### 7.3. Gọi trong transaction

Ví dụ Java SE dùng persistence unit `RESOURCE_LOCAL`:

```java
EntityManager em = emf.createEntityManager();

try {
    var tx = em.getTransaction();

    tx.begin();
    try {
        int code = new InventoryProcedureCaller()
            .reserveStock(em, 101L, 5);

        if (code != 0) {
            // Quy tắc ứng dụng: không commit thao tác
            // nghiệp vụ thất bại.
            tx.rollback();

            throw new IllegalStateException(
                "Reservation rejected, code=" + code
            );
        }

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackEx) {
                ex.addSuppressed(rollbackEx);
            }
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Ở đây ứng dụng **điều khiển transaction**; lời gọi Java không bảo đảm routine không có lệnh commit/rollback nội bộ. Đây là một điều kiện cần kiểm tra trong phần thân thủ tục của từng DBMS.

Với Spring/JTA EntityManager do container quản lý, **không gọi `em.getTransaction().begin()`**; ranh giới giao dịch được khai báo và quản lý ở tầng framework.

### 7.4. Không dùng status code thay cho xác nhận commit

Nếu OUT trả `0 = RESERVED` nhưng `commit()` thất bại, không được thông báo “giữ hàng đã hoàn tất”. Giá trị OUT mô tả kết quả thực thi procedure **trong giao dịch đang tiến hành**. Commit mới là bước xác nhận persistence thành công.

## 8. Named parameters và positional parameters

JPA cho phép đăng ký theo tên hoặc vị trí trong những trường hợp được hỗ trợ.

### 8.1. Theo tên

```java
sp.registerStoredProcedureParameter(
    "productId",
    Long.class,
    ParameterMode.IN
);

sp.registerStoredProcedureParameter(
    "requestedAmount",
    Integer.class,
    ParameterMode.IN
);

sp.registerStoredProcedureParameter(
    "statusCode",
    Integer.class,
    ParameterMode.OUT
);

sp.setParameter("productId", 101L);
sp.setParameter("requestedAmount", 5);
```

Ưu điểm:

- Code dễ đọc.
- Không dễ nhầm `1` với `2`.
- Hợp đồng rõ hơn khi procedure có nhiều tham số.

Nhưng ở mức tích hợp phải kiểm tra:

- Tên JPA có khớp tên mà provider/driver biết không?
- DBMS có phân biệt chữ hoa/chữ thường hoặc yêu cầu quoting?
- Parameter name metadata có được driver cung cấp không?
- Tên có gắn tiền tố `@`, `:` hay schema/package-specific convention không?
- Provider/dialect có hỗ trợ named registration ổn định không?

**Tính năng có mặt trong API không bảo đảm mọi combo provider/driver/database hỗ trợ đầy đủ.**

### 8.2. Theo vị trí

```java
sp.registerStoredProcedureParameter(1, Long.class, ParameterMode.IN);
sp.registerStoredProcedureParameter(2, Integer.class, ParameterMode.IN);
sp.registerStoredProcedureParameter(3, Integer.class, ParameterMode.OUT);
```

Ưu điểm:

- Không cần dựa vào tên tham số database.
- Có thể phù hợp với driver/provider có hỗ trợ named parameters không ổn định.
- Dễ định nghĩa hợp đồng đơn giản.

Rủi ro:

- Đổi thứ tự tham số trên DBMS khiến Java gọi sai.
- Procedure có parameters tùy chọn/default hoặc OUT khác signature có thể cần handling riêng.
- Chữ ký function/cursor có thể không tương đồng với procedure.

**Không trộn tên và vị trí một cách tùy tiện** trong cùng một lời gọi nếu chưa xác định rõ quy tắc provider.

### 8.3. Quy tắc thiết kế

Nếu hệ thống thật sự cần hỗ trợ nhiều DBMS:

1. Đặt hợp đồng tham số rõ ràng trong code và tài liệu migration.
2. Chọn **một quy tắc nhất quán** cho mỗi adapter.
3. Không để tầng service biết routine dùng `"p_id"` hay `"@Id"`.
4. Kiểm thử chữ ký sau mỗi lần nâng phiên bản routine/driver.
5. Nếu một DBMS cần registration khác, đưa khác biệt vào adapter tương ứng.

## 9. IN, OUT và INOUT: khác biệt kiểu dữ liệu

`ParameterMode` là chuẩn JPA:

```java
ParameterMode.IN
ParameterMode.OUT
ParameterMode.INOUT
ParameterMode.REF_CURSOR
```

Nhưng mode không tự giải quyết mọi type conversion.

### 9.1. IN

Giá trị từ Java xuống database:

```java
sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
sp.setParameter(1, 101L);
```

Cần kiểm tra mapping `Long` sang `BIGINT` hoặc kiểu số phù hợp, đặc biệt nếu DBMS dùng kiểu numeric tổng quát hơn.

### 9.2. OUT

Khai báo:

```java
sp.registerStoredProcedureParameter(
    2, Integer.class, ParameterMode.OUT
);
```

Lấy:

```java
Object output = sp.getOutputParameterValue(2);
```

Nếu procedure cho phép trả `NULL`, cần xử lý null. Nếu driver trả một lớp numeric khác, cần xem contract/provider thay vì ép kiểu bất chấp.

### 9.3. INOUT

```java
sp.registerStoredProcedureParameter(
    3, BigDecimal.class, ParameterMode.INOUT
);

sp.setParameter(
    3,
    new BigDecimal("100.00")
);
```

Sau khi thực thi:

```java
Object adjusted = sp.getOutputParameterValue(3);
```

`INOUT` yêu cầu cả binding đầu vào và retrieval đầu ra. Cách DBMS định nghĩa INOUT và giá trị được cập nhật cần được giữ nhất quán trong procedure.

### 9.4. Null và default parameter

Một số routine có giá trị mặc định ở SQL signature. Không nên giả định rằng:

```java
sp.setParameter(2, null);
```

tương đương với **không truyền parameter** để database tự dùng giá trị mặc định.

Hai trường hợp có thể khác nhau:

- **Truyền null thực sự:** procedure nhận một NULL và có thể xử lý riêng.
- **Bỏ hẳn tham số:** DBMS có thể chọn default nếu lời gọi/syntax hỗ trợ.

Vì JPA/provider phải tạo một lời gọi với signature cụ thể, khả năng bỏ một parameter có default cần được kiểm thử trên từng database. Nếu API muốn giá trị mặc định nhất quán giữa hệ quản trị, thường dễ hơn khi **tính default ở Java** hoặc định nghĩa rõ trong hợp đồng routine.

## 10. Kiểu dữ liệu: phạm vi portable và không portable

Các kiểu dữ liệu đơn giản không đồng nghĩa *mọi conversion đều tự động*.

| Java/domain type | Stored procedure parameter phổ biến | Mức rủi ro khả chuyển |
| --- | --- | --- |
| `Integer`/`Long` | INTEGER/BIGINT/NUMBER | Thấp đến trung bình; xem range, precision. |
| `BigDecimal` | DECIMAL/NUMERIC/NUMBER | Trung bình; scale/rounding và driver conversion. |
| `String` | VARCHAR/NVARCHAR/TEXT | Trung bình; Unicode/collation/length. |
| `Boolean` | BOOLEAN/BIT/NUMBER(1)/CHAR | Trung bình đến cao; representation khác nhau. |
| `LocalDate` | DATE | Trung bình; provider/JDBC support. |
| `LocalDateTime` | TIMESTAMP/DATETIME2 | Trung bình; timezone không có trong `LocalDateTime`. |
| `OffsetDateTime` | TIMESTAMP WITH TIME ZONE và biến thể | Cao hơn; semantics timezone khác nhau. |
| `byte[]` | BLOB/VARBINARY | Trung bình; stream/size/resource handling. |
| `UUID` | UUID/UNIQUEIDENTIFIER/RAW/CHAR | Cao hơn nếu yêu cầu cùng mapping binary/native. |
| Arrays/collections | SQL ARRAY/table-valued parameters | Cao; nhiều extension DBMS/driver. |
| JSON/XML | JSON/JSONB/XML/NVARCHAR/CLOB | Cao; kiểu native và operator khác nhau. |
| Composite/record/STRUCT | UDT/record/STRUCT | Cao; thường phải viết adapter riêng. |
| Cursor | REF CURSOR/driver-specific handle | Cao; phụ thuộc rất mạnh DBMS/provider. |

### 10.1. Money và BigDecimal

Giả sử nghiệp vụ cần trả phí sau chiết khấu:

```text
amount = 123456.78
```

Java nên dùng `BigDecimal` thay vì `double` cho phép tính chính xác theo đơn vị tiền tệ.

Nhưng cần xác nhận:

- SQL type có đủ precision/scale không?
- Procedure có làm tròn ở bước nào?
- Provider/driver có trả `BigDecimal` hay một wrapper khác?
- Nếu amount vượt ngưỡng, lỗi được báo ở đâu?

Giữ cùng một class Java không bảo đảm cùng quy tắc làm tròn của mọi DBMS.

### 10.2. Timestamp, múi giờ và độ chính xác

`LocalDateTime` **không chứa timezone**. Nếu procedure dùng `CURRENT_TIMESTAMP` ở mỗi DBMS và so sánh với dữ liệu giờ địa phương, sự khác nhau về session timezone hoặc độ chính xác timestamp có thể làm kết quả thay đổi.

Nếu hệ thống cần một mốc thời gian tuyệt đối, phải quy định rõ:

- Kiểu Java.
- Kiểu SQL theo từng DBMS.
- Quy tắc chuyển UTC/timezone.
- Độ chính xác giây/millisecond/microsecond.
- Cách định nghĩa khoảng thời gian, ví dụ `[from, to)`.

Đây là vấn đề **behavioral portability**, không chỉ bind parameter.

### 10.3. Enum

Nếu Java có:

```java
enum ReservationStatus {
    RESERVED,
    NOT_FOUND,
    OUT_OF_STOCK
}
```

DBMS có thể lưu enum dưới dạng string, smallint hoặc native enum type. Với routine xuyên DBMS, thường nên dùng một contract có mã status rõ và convert ở adapter/domain, thay vì giả định provider tự bind Java enum thành đúng vendor SQL enum.

### 10.4. Collection và table-valued parameters

SQL Server có **table-valued parameters**; PostgreSQL có **array types** và các cách nhận tập; Oracle có **collection/UDT types**. Chúng giải quyết bài toán truyền nhiều IDs nhưng **không có một dạng stored procedure parameter duy nhất mà `StoredProcedureQuery` tiêu chuẩn hỗ trợ y hệt trên mọi database**.

Nếu cần bulk 100.000 IDs, đừng chỉ tìm cách ép một `List<Long>` qua `setParameter()` rồi tuyên bố portable. Có thể chọn:

- Staging table với khóa batch.
- Chuỗi lệnh batch/JDBC phù hợp.
- Tập parameter theo vendor adapter.
- Cơ chế bulk insert rồi procedure xử lý batch ID.

Lựa chọn nào tốt phụ thuộc độ lớn dữ liệu, transaction và hạ tầng.

## 11. Procedure khác function: một ranh giới quan trọng

Các DBMS không thống nhất hoàn toàn việc dùng:

- **Procedure:** gọi để thực hiện thao tác, có thể có OUT parameters hoặc result sets.
- **Function:** có giá trị trả về; ở một số hệ quản trị có thể trả bảng, cursor hoặc composite value.

Ví dụ nghiệp vụ:

```text
get_customer_discount(customerId) -> decimal
```

Trên một DBMS nó có thể được viết như function trả numeric. Trên DBMS khác có thể là procedure với một OUT parameter.

### 11.1. Vì sao không coi chúng tương đương tuyệt đối?

Cú pháp caller khác:

```sql
SELECT get_customer_discount(101);
```

so với:

```text
CALL get_customer_discount(101, OUT discount)
```

Một provider có thể hỗ trợ function call thông qua cơ chế native query/dialect riêng; **`StoredProcedureQuery` không phải abstraction chung cho mọi dạng SQL function trong mọi ngữ cảnh**.

### 11.2. Thiết kế theo nghiệp vụ, không theo hình dạng SQL

Domain-facing API có thể là:

```java
BigDecimal calculateDiscount(long customerId);
```

Adapter PostgreSQL có thể dùng SELECT function; adapter SQL Server có thể dùng một cách gọi khác; adapter khác dùng JPA query hoặc Java logic.

**Giữ hợp đồng Java độc lập với việc DBMS gọi nó là function hay procedure** giúp khả chuyển ở tầng ứng dụng.

## 12. REF_CURSOR: tính năng chuẩn ở API, phụ thuộc mạnh khi chạy

`ParameterMode.REF_CURSOR` tồn tại trong API JPA. Nhưng **hỗ trợ thực tế của cursor output** liên quan tới DBMS và driver.

Một ví dụ khai báo kiểu mode:

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("list_open_orders");

sp.registerStoredProcedureParameter(
    1,
    void.class,
    ParameterMode.REF_CURSOR
);
```

Đây là **đoạn minh họa API**, không phải lời gọi runnable trên mọi DBMS: tên routine, vị trí cursor, class đăng ký, quyền truy cập và cách nhận result set phụ thuộc provider/database.

### 12.1. Vì sao REF_CURSOR khó portable?

Với các DBMS khác nhau, có thể có:

- Cursor được gán qua OUT parameter.
- Cursor tồn tại trong phạm vi transaction.
- Procedure trả SELECT result sets trực tiếp mà không dùng OUT cursor.
- Function trả bảng được truy vấn qua `SELECT`.
- Driver yêu cầu đăng ký JDBC-specific type hoặc tham số đặc biệt.
- Provider chỉ hỗ trợ một số dạng cursor/result mapping.

Vì thế **“JPA có REF_CURSOR” không đủ để kết luận ứng dụng có thể đổi giữa Oracle, PostgreSQL và SQL Server mà không sửa phần tích hợp**.

### 12.2. Cách giảm phụ thuộc

Nếu ứng dụng chỉ cần một danh sách hàng và schema dữ liệu đơn giản, cân nhắc:

- JPQL/Criteria query trực tiếp thay procedure.
- Native SELECT kèm DTO/`@SqlResultSetMapping`.
- Adapter DBMS-specific để tiêu thụ cursor và trả `List<OrderSummary>`.
- Thống nhất contract JSON/DTO ở tầng application, không để cursor object lan ra service/controller.

Nếu vẫn dùng REF_CURSOR, phải đưa nó vào **danh mục rủi ro khả chuyển cao** và viết integration tests cho từng DBMS/provider/version mục tiêu.

## 13. Nhiều result sets và update counts

Một procedure có thể:

```text
UPDATE -> result set #1 -> UPDATE -> result set #2
```

JPA có cơ chế:

```java
boolean isResultSet = sp.execute();

while (true) {
    if (isResultSet) {
        List<?> rows = sp.getResultList();
        // Xử lý result set hiện tại.
    } else {
        int count = sp.getUpdateCount();
        if (count == -1) {
            break;
        }
        // Xử lý update count hiện tại, kể cả count = 0.
    }

    isResultSet = sp.hasMoreResults();
}
```

Đây là pattern tiêu chuẩn để duyệt các phần kết quả được provider phơi bày.

### 13.1. Boolean của execute() không phải status nghiệp vụ

Nếu `sp.execute()` trả `false`, điều đó **không đồng nghĩa thủ tục thất bại**. Kết quả đầu tiên có thể là update count hoặc không có result set.

### 13.2. false của hasMoreResults() không phải lúc nào cũng là hết

`hasMoreResults()` chuyển sang phần kế tiếp. Nó trả `false` nếu phần kế tiếp **không phải result set**; trong trường hợp ấy cần gọi `getUpdateCount()`. Chỉ khi không có result set và update count là `-1` mới dừng vòng lặp này.

### 13.3. Update count bằng 0 vẫn là một kết quả

Một `UPDATE` không tác động dòng nào có thể cho update count `0`. Nếu code dùng:

```java
if (count <= 0) break;
```

thì có thể bỏ qua result sets phía sau. Dùng đúng sentinel `-1`.

### 13.4. Vì sao khả chuyển bị giới hạn?

- SQL Server có thể gửi nhiều result sets và row-count messages.
- Một DBMS/provider có thể dùng cursor OUT thay vì SELECT result set trực tiếp.
- Driver có thể phơi bày hoặc suppress một số update counts.
- Mapping nhiều result sets có thể phụ thuộc provider và chữ ký của routine.
- Quy tắc khi lấy OUT parameter có thể cần tiêu thụ các phần kết quả trước.

**Thiết kế routine trả “result set thứ hai là danh sách audit” cần integration tests với driver/provider thật.** Đừng dựa vào mock Java để xác nhận thứ tự do DBMS phát ra.

## 14. Update counts không phải hợp đồng nghiệp vụ chung

Giả sử routine làm:

```text
UPDATE inventory       -> 1
INSERT reservation_log -> 1
UPDATE batch_summary   -> 1
```

Tổng update counts là 3, nhưng chỉ có **một sản phẩm được giữ hàng**.

Do đó, không nên:

```java
int businessAffected = count1 + count2 + count3;
```

nếu mỗi count thuộc một bảng khác nhau.

### 14.1. SQL Server SET NOCOUNT

Trong T-SQL:

```sql
SET NOCOUNT ON;
```

có thể suppress row-count messages. Điều đó **không làm câu UPDATE biến mất**, mà thay đổi phần thông tin số dòng gửi tới client.

Cùng một routine, đổi NOCOUNT hoặc thêm trigger có thể làm số update counts mà driver phơi bày thay đổi.

### 14.2. Khuyến nghị về contract

Nếu nghiệp vụ cần số lượng cụ thể, hãy định nghĩa một OUT parameter:

```text
AffectedInventoryRows OUT INTEGER
```

hoặc một result set tường minh:

```text
status_code | affected_inventory_rows
------------+------------------------
0           | 1
```

Mục đích là **định nghĩa ý nghĩa dữ liệu đầu ra**, không dựa vào số lượng statement trong thân thủ tục.

## 15. @SqlResultSetMapping: portable về API nhưng phụ thuộc shape SQL

Giả sử routine trả các cột:

```text
order_id | customer_name | total_amount
```

JPA có thể dùng `@SqlResultSetMapping` để ánh xạ sang DTO:

```java
@SqlResultSetMapping(
    name = "OrderSummaryMapping",
    classes = @ConstructorResult(
        targetClass = OrderSummary.class,
        columns = {
            @ColumnResult(name = "order_id", type = Long.class),
            @ColumnResult(name = "customer_name", type = String.class),
            @ColumnResult(name = "total_amount", type = BigDecimal.class)
        }
    )
)
```

Annotation phải đặt tại vị trí metadata JPA hợp lệ, ví dụ trên một managed entity. `OrderSummary` cần constructor phù hợp. Code trên là **fragment**, không phải một Java class độc lập.

### 15.1. Cái gì có tính chuẩn?

- Cú pháp metadata mapping của JPA.
- Ý nghĩa entity, column, constructor mapping theo API.
- Cách tạo query dùng tên mapping.

### 15.2. Cái gì vẫn cần kiểm tra?

- Routine có trả **đúng ba cột** và tên alias đó không?
- DBMS có đổi cách viết hoa hoặc quoting alias không?
- Kiểu `NUMERIC` trả về có tương thích `BigDecimal` không?
- `BIGINT` có được provider convert đúng sang `Long` không?
- Hai result sets có dùng hai mapping khác nhau đúng thứ tự không?
- Một DBMS mới có trả thêm cột thông báo hay thay alias không?

Một mapping có cú pháp hợp lệ vẫn có thể thất bại hoặc cho dữ liệu sai khi đổi routine/sql dialect.

### 15.3. Đừng map báo cáo thiếu cột thành managed entity

Nếu SELECT chỉ trả `order_id` và `total_amount`, việc cố map thành một `OrderEntity` managed hoàn chỉnh có thể thiếu cột bắt buộc hoặc gây hiểu sai state. DTO thường phù hợp hơn với result set báo cáo/tổng hợp.

## 16. NamedStoredProcedureQuery: thống nhất metadata, không thống nhất SQL

Ví dụ:

```java
@NamedStoredProcedureQuery(
    name = "Inventory.reserve",
    procedureName = "reserve_stock",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            type = Integer.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            type = Integer.class
        )
    }
)
```

Ứng dụng có thể gọi:

```java
StoredProcedureQuery sp =
    em.createNamedStoredProcedureQuery("Inventory.reserve");
```

Nhưng trên DBMS mới, routine `reserve_stock` vẫn phải:

- Được triển khai và cấp quyền.
- Có đúng thứ tự/kiểu tham số.
- Trả status codes theo contract.
- Áp dụng transaction/locking đúng.
- Trả OUT/result sets theo cách provider hỗ trợ.

**NamedStoredProcedureQuery giảm sự lặp lại của metadata lời gọi, không biến thân routine thành SQL khả chuyển.**

### 16.1. Cần version contract

Nếu chữ ký thay đổi:

```text
V1: reserve_stock(productId, qty, statusCode OUT)
V2: reserve_stock(tenantId, productId, qty, statusCode OUT)
```

mọi adapter phải được cập nhật cùng migration. Nếu ứng dụng triển khai rolling upgrade, có thể cần chạy song song `reserve_stock_v1` và `reserve_stock_v2` cho tới khi toàn bộ nodes cập nhật.

Đừng đổi thứ tự positional parameters mà không thay version. Đây là lỗi runtime có thể gây ghi nhầm dữ liệu rất nghiêm trọng nếu hai tham số cùng kiểu số.

## 17. Transaction semantics là giới hạn khả chuyển lớn

Stored procedure có thể thực hiện:

- SELECT.
- INSERT/UPDATE/DELETE.
- Khóa hàng/bảng.
- Tạo bảng tạm.
- Thực thi SQL động.
- Gọi routines khác.
- Thử xử lý transaction nội bộ.

Độ khả chuyển phụ thuộc cách các thao tác này tương tác với transaction của ứng dụng.

### 17.1. Transaction do JPA quản lý

Trong Java SE:

```java
EntityTransaction tx = em.getTransaction();

tx.begin();
try {
    // Gọi stored procedure.
    tx.commit();
} catch (RuntimeException e) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw e;
}
```

Đây là mô hình của `RESOURCE_LOCAL`.

Trong Spring/JTA:

```java
@Transactional
public ReservationResult reserve(...) {
    // Gọi procedure bằng EntityManager.
}
```

Transaction manager của framework/container điều phối commit/rollback. Không tự gọi `getTransaction().begin()` trên JTA EntityManager.

### 17.2. Thủ tục có COMMIT nội bộ

Nếu routine tự `COMMIT` trong thân, quy tắc phụ thuộc DBMS và hoàn cảnh lời gọi:

- Có DBMS cho phép trong một số ngữ cảnh nhưng cấm trong ngữ cảnh khác.
- Có routine/function không được tự điều khiển transaction.
- Có transaction implicit hoặc DDL gây implicit commit.
- Có cách xử lý exception làm một statement rollback nhưng transaction còn hoạt động, hoặc transaction chuyển sang trạng thái không thể commit.

**Không thể giả định một đoạn SQL procedure có lệnh COMMIT sẽ hoạt động giống nhau khi gọi từ JPA trên mọi DBMS.**

Nếu cần tính khả chuyển, thường nên **để ứng dụng/transaction manager sở hữu ranh giới transaction**, tránh transaction control vendor-specific trong routine trừ khi thực sự có yêu cầu và test rõ.

### 17.3. Flush trước lời gọi

Giả sử ứng dụng sửa một managed entity:

```java
InventoryBalance balance =
    em.find(InventoryBalance.class, 101L);

balance.setAvailableQuantity(12);

// Cần routine nhìn thấy state mới trong transaction:
em.flush();

callReserveStock(em, 101L, 5);
```

`flush()` đồng bộ các thay đổi JPA đang chờ tới database nhưng **không commit**. Nếu routine đọc bảng ngay sau đó, việc flush chủ động có thể giúp đảm bảo nó thấy state mà business flow yêu cầu.

Không dựa vào giả định mọi provider sẽ auto-flush theo cùng một lịch trước **mọi** stored procedure call, nhất là khi query hint/flush mode khác nhau.

### 17.4. State stale sau lời gọi

Nếu routine trực tiếp cập nhật bảng, một managed entity đã được tải có thể không tự thay đổi field trong Java:

```java
InventoryBalance b =
    em.find(InventoryBalance.class, 101L);

callReserveStock(em, 101L, 5);

// b.getAvailableQuantity() có thể là state cũ.
```

Có thể cần:

```java
em.refresh(b);
```

hoặc dùng EntityManager/persistence context mới ở bước đọc tiếp theo. Nhưng `refresh` có thể ghi đè thay đổi chưa đồng bộ; `clear` detach các managed entities. Phải thiết kế theo luồng transaction, không gọi bừa cả hai.

### 17.5. Locking và isolation

Một thuật toán giữ kho sai:

```text
SELECT available
if available >= qty:
    UPDATE available = available - qty
```

có thể có race condition giữa hai transaction nếu không có locking hoặc atomic condition phù hợp.

Một hướng ở database:

```sql
UPDATE inventory_balance
SET available_quantity = available_quantity - :qty,
    reserved_quantity = reserved_quantity + :qty
WHERE product_id = :id
  AND available_quantity >= :qty;
```

SQL trên là ý tưởng theo cú pháp bind của một query, **không phải copy-paste nguyên dạng vào mọi SQL procedure**. Routine phải kiểm tra affected rows và trả status theo domain contract.

Bất kể dùng Oracle, PostgreSQL hay SQL Server, cần xác nhận thuật toán tránh **lost update/negative stock**, không chỉ xác nhận Java nhận được OUT code.

## 18. Exception và error codes không tự portable

Một routine có thể phát lỗi:

- Sản phẩm không tồn tại.
- Không đủ tồn kho.
- Vi phạm unique constraint.
- Deadlock.
- Lock timeout.
- Lỗi chuyển kiểu dữ liệu.
- Quyền execute bị từ chối.
- Procedure không tồn tại.
- Kết nối database bị mất.

JPA provider có thể bọc chúng thành `PersistenceException` hoặc một exception liên quan. Nguyên nhân gốc có thể là `SQLException` với `SQLState` và vendor-specific code.

### 18.1. Không so sánh vendor code ở domain service

Không nên để logic nghiệp vụ viết cứng:

```java
if (sqlException.getErrorCode() == 2627) {
    // Logic chỉ áp dụng cho một SQL Server error code.
}
```

rồi mong nó hoạt động trên PostgreSQL/Oracle/MySQL.

Thay vào đó, đặt một tầng dịch:

```text
Vendor error / SQLException
           |
           v
DBMS-specific adapter
           |
           v
Domain exception / status
    OutOfStock
    DuplicateReservation
    TemporaryDatabaseConflict
```

Đối với lỗi nghiệp vụ dự đoán được, có thể dùng status OUT rõ ràng; đối với lỗi hạ tầng, nên phân loại exception có chủ đích và đảm bảo rollback phù hợp.

### 18.2. Retry không phải mặc định

Một transaction deadlock có thể có cơ chế retry hữu ích, nhưng không thể retry vô điều kiện nếu procedure:

- Gửi email.
- Gọi external API.
- Phát sự kiện ngoài transaction.
- Ghi dữ liệu idempotency chưa được thiết kế.
- Có thao tác không thể hoàn nguyên.

Retry cần phân loại lỗi và thiết kế idempotency/concurrency. Bảo đảm này nằm ngoài `StoredProcedureQuery`.

## 19. Quyền truy cập, schema và routine naming

Tên procedure:

```java
em.createStoredProcedureQuery("reserve_stock");
```

có thể được DBMS phân giải dựa trên:

- Default schema của user/session.
- Search path.
- Package/owner.
- Quoted identifiers.
- Case sensitivity.
- Current catalog/database.
- Synonym hoặc alias có hiệu lực.

### 19.1. Schema-qualified name

Một hệ thống có thể yêu cầu:

```java
em.createStoredProcedureQuery(
    "inventory.reserve_stock"
);
```

Hệ khác có thể có package name, schema name hoặc naming convention khác. Không đưa tên đầy đủ của database vào domain interface; đặt nó ở adapter/configuration phù hợp.

### 19.2. Quyền EXECUTE

Một role có thể cần quyền `EXECUTE` trên routine, bên cạnh hoặc thay vì quyền đọc/ghi trực tiếp bảng.

Đối với procedure chạy với quyền owner/definer, ranh giới bảo mật còn phụ thuộc:

- Người gọi thực sự được phép thao tác loại dữ liệu nào?
- Procedure có tự kiểm tra tenant/ownership không?
- Có SQL động dùng input chưa kiểm tra không?
- Có rò rỉ dữ liệu qua result sets hoặc error messages không?

**“Dùng stored procedure” không mặc nhiên khiến ứng dụng an toàn hơn**, nhất là khi routine chạy với quyền cao.

### 19.3. Injection trong procedure

JPA parameter binding giúp tránh nối chuỗi đầu vào vào **lời gọi**. Nhưng nếu bên trong routine viết SQL động:

```text
"SELECT ... WHERE name = '" + inputName + "'"
```

thì rủi ro injection vẫn còn **ở tầng database**. Mỗi DBMS có cơ chế bind dynamic SQL riêng cần sử dụng đúng.

## 20. Hợp đồng kết quả: versioning quan trọng hơn tên API

Giả sử routine V1 trả:

```text
status_code OUT INTEGER
```

V2 đổi thành:

```text
status_code OUT VARCHAR
message OUT VARCHAR
```

Java gọi `registerStoredProcedureParameter(..., Integer.class, ...)` sẽ không còn tương thích nếu adapter chưa được sửa.

Các loại thay đổi gây breaking change:

- Đổi thứ tự parameters.
- Đổi IN thành INOUT hoặc ngược lại.
- Đổi SQL type/precision/scale.
- Đổi tên/schema/package routine.
- Thêm/đổi thứ tự result sets.
- Đổi alias/kiểu cột trong result set.
- Đổi semantics status code.
- Đổi transaction ownership.
- Đổi cách xử lý null/default arguments.
- Thay isolation/locking khiến side effects khác trước.

### 20.1. Viết contract độc lập DBMS

Ví dụ:

```yaml
operation: reserveStock
version: 1
inputs:
  productId: int64
  requestedQuantity: int32
outputs:
  statusCode:
    type: int32
    values:
      0: RESERVED
      1: PRODUCT_NOT_FOUND
      2: INSUFFICIENT_STOCK
      3: INVALID_QUANTITY
transaction:
  owner: application
  invariant:
    - availableQuantity >= 0
    - reservedQuantity >= 0
errorPolicy:
  retryableInfrastructureErrors: adapter_defined
```

Đây là **YAML ví dụ mô tả contract**, không phải file phải tạo trong repository. Hợp đồng này dùng để triển khai và kiểm thử cùng một hành vi trên những adapters khác nhau.

### 20.2. Migration theo DBMS

Có thể tổ chức migration:

```text
migrations/
    postgresql/
        V001__inventory_tables.sql
        V002__reserve_stock_function_or_procedure.sql
    sqlserver/
        V001__inventory_tables.sql
        V002__reserve_stock_procedure.sql
    oracle/
        V001__inventory_tables.sql
        V002__reserve_stock_package.sql
```

Ví dụ thư mục chỉ minh họa tổ chức triển khai; không phải yêu cầu đổi cấu trúc project ở bài này.

Điểm quan trọng là **cùng một version domain contract được thực hiện bằng migration riêng cho từng DBMS**. Đây thường là hướng thực tế hơn việc cố tạo một file SQL thủ tục chạy nguyên vẹn trên mọi hệ.

## 21. Kiến trúc Port–Adapter để cô lập khác biệt DBMS

Khi cần đổi DBMS mà không viết lại toàn bộ domain, hãy cô lập lời gọi stored procedure sau một interface có nghĩa nghiệp vụ.

### 21.1. Domain contract

```java
package com.example.inventory;

public interface StockReservationPort {
    ReservationOutcome reserve(
        long productId,
        int quantity
    );
}
```

DTO:

```java
package com.example.inventory;

public enum ReservationOutcome {
    RESERVED,
    PRODUCT_NOT_FOUND,
    INSUFFICIENT_STOCK,
    INVALID_QUANTITY
}
```

Service chỉ gọi interface:

```java
package com.example.inventory;

public final class ReservationService {
    private final StockReservationPort port;

    public ReservationService(
            StockReservationPort port) {
        this.port = port;
    }

    public ReservationOutcome reserve(
            long productId,
            int quantity) {

        if (productId <= 0 || quantity <= 0) {
            return ReservationOutcome.INVALID_QUANTITY;
        }

        return port.reserve(productId, quantity);
    }
}
```

Không có `StoredProcedureQuery`, `REF_CURSOR` hay tên vendor procedure trong service.

### 21.2. JPA adapter

```java
package com.example.inventory;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

public final class JpaStockReservationAdapter
        implements StockReservationPort {

    private final EntityManager em;

    public JpaStockReservationAdapter(EntityManager em) {
        this.em = em;
    }

    @Override
    public ReservationOutcome reserve(
            long productId,
            int quantity) {

        StoredProcedureQuery sp =
            em.createStoredProcedureQuery("reserve_stock");

        sp.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN
        );
        sp.registerStoredProcedureParameter(
            2, Integer.class, ParameterMode.IN
        );
        sp.registerStoredProcedureParameter(
            3, Integer.class, ParameterMode.OUT
        );

        sp.setParameter(1, productId);
        sp.setParameter(2, quantity);

        boolean isResultSet = sp.execute();

        while (true) {
            if (isResultSet) {
                sp.getResultList();
            } else if (sp.getUpdateCount() == -1) {
                break;
            }

            isResultSet = sp.hasMoreResults();
        }

        Object output = sp.getOutputParameterValue(3);
        if (!(output instanceof Number n)) {
            throw new IllegalStateException(
                "Invalid reserve_stock OUT value"
            );
        }

        return switch (n.intValue()) {
            case 0 -> ReservationOutcome.RESERVED;
            case 1 -> ReservationOutcome.PRODUCT_NOT_FOUND;
            case 2 -> ReservationOutcome.INSUFFICIENT_STOCK;
            case 3 -> ReservationOutcome.INVALID_QUANTITY;
            default -> throw new IllegalStateException(
                "Unknown status code: " + n
            );
        };
    }
}
```

Đây là adapter minh họa. Khi triển khai vào Spring, `EntityManager` có thể được inject và transaction được quản lý ở service. Với Java SE, dùng EntityManager được tạo trong scope/transaction phù hợp.

### 21.3. Adapter riêng cho các DBMS

Nếu PostgreSQL thực hiện logic bằng một function trả scalar thay vì procedure OUT, có thể tạo:

```java
public final class PostgreSqlReservationAdapter
        implements StockReservationPort {
    // Gọi function theo cách phù hợp với PostgreSQL.
    // Chuyển kết quả về ReservationOutcome.
}
```

Nếu SQL Server có procedure dùng named OUT và driver behavior riêng:

```java
public final class SqlServerReservationAdapter
        implements StockReservationPort {
    // Gọi procedure T-SQL theo contract.
    // Xử lý update counts/OUT đúng.
}
```

Đây là phác thảo class, không phải đoạn code đủ biên dịch độc lập. Ý tưởng là **không bắt domain service mang chi tiết JDBC/provider**.

### 21.4. Chọn implementation theo môi trường

Ứng dụng có thể cấu hình một adapter tương ứng database khi khởi động, thay vì viết:

```java
if (isPostgres) {
    // SQL khác...
} else if (isSqlServer) {
    // SQL khác...
}
```

ở mọi use case.

Ưu điểm:

- Khác biệt vendor tập trung một chỗ.
- Dễ viết tests cho cùng domain contract.
- Có thể chuyển một chức năng từ procedure sang JPQL/JDBC mà không đổi service.
- Có chỗ riêng để chuyển vendor error codes sang domain errors.

**Nhược điểm:** tăng số implementation/migration và chi phí duy trì. Chỉ nên đầu tư lớp adapter đa DBMS nếu có yêu cầu khả chuyển thực tế, không phải chỉ vì mong muốn trừu tượng.

## 22. Khi nào không nên dùng stored procedure?

Stored procedure phù hợp khi có lợi ích cụ thể, nhưng không phải mọi CRUD đều cần nó.

### 22.1. Các use case nên cân nhắc JPQL/Criteria

Ví dụ:

- Tìm sản phẩm theo danh mục và khoảng giá.
- Lấy danh sách orders cho một trang.
- Đếm số records theo trạng thái.
- Tải entity graph theo một fetch plan.
- Cập nhật một entity managed có optimistic locking đơn giản.

JPA/JPQL/Criteria có khả năng khả chuyển tương đối cao hơn vì provider dịch câu query theo mapping/dialect.

Ví dụ:

```jpql
SELECT p
FROM Product p
WHERE p.status = :status
  AND p.price >= :minimumPrice
```

thường dễ duy trì đa DBMS hơn một stored procedure chuyên dụng chỉ để chạy đúng câu SELECT này.

### 22.2. Khi stored procedure có lợi thế

- Logic DML phức tạp cần xử lý gần dữ liệu.
- Thuật toán bulk processing có nhiều bước và muốn giảm round-trips.
- Dựa vào tính năng DBMS đặc biệt mà JPA không biểu diễn tốt.
- Có procedure kế thừa từ hệ thống legacy.
- Chính sách quyền truy cập database yêu cầu encapsulate thao tác qua routine.
- Nhu cầu hiệu năng đã đo chứng minh lợi ích.

Lúc đó, **chấp nhận phụ thuộc DBMS có kiểm soát** có thể hợp lý hơn cố đạt khả chuyển tuyệt đối.

### 22.3. Khi JDBC có thể phù hợp hơn JPA StoredProcedureQuery

- Cần xử lý nhiều REF_CURSOR/result sets phức tạp.
- Cần streaming rows với cursor/driver-specific settings.
- Cần table-valued parameters hoặc vendor SQL types.
- Cần truy cập `CallableStatement`/`ResultSetMetaData`/SQL warnings.
- Provider JPA không hỗ trợ một kiểu OUT hoặc function call cụ thể.

Nếu ứng dụng đang dùng Spring/JPA, cần phối hợp **connection/transaction manager** khi dùng JDBC; không tự mở một connection ngoài transaction rồi nghĩ có atomicity chung.

## 23. Ma trận rủi ro khả chuyển

Một bảng đánh giá ban đầu có thể như sau.

| Đặc điểm lời gọi | Rủi ro | Giải thích |
| --- | --- | --- |
| Procedure có 2 IN số nguyên, 1 OUT số nguyên | **Thấp–trung bình** | API đơn giản; vẫn cần kiểm tra OUT và chữ ký. |
| Dùng tên parameters | **Trung bình** | Metadata/naming/case/provider khác nhau. |
| Dùng positional parameters | **Thấp–trung bình** | Phụ thuộc thứ tự signature. |
| Function trả scalar qua SELECT | **Trung bình–cao** | Không phải một dạng `StoredProcedureQuery` duy nhất. |
| Procedure trả một result set đơn giản | **Trung bình** | Mapping/driver phải khớp. |
| Nhiều result sets và update counts xen kẽ | **Cao** | Behavior/ordering/NOCOUNT/driver. |
| `REF_CURSOR` | **Cao** | Cursor lifecycle và provider/database-specific. |
| Array/JSON/UDT parameter | **Cao** | Kiểu SQL/driver khác nhau. |
| Procedure có COMMIT/ROLLBACK bên trong | **Cao** | Transaction semantics khác nhau. |
| Vendor-specific dynamic SQL | **Cao** | Cú pháp, quyền, lỗi, optimizer. |
| OUT status code do ứng dụng định nghĩa | **Thấp ở tầng domain** | Phải triển khai đúng trên mọi DBMS. |
| DBMS-specific SQL migration | **Chấp nhận được nếu cô lập** | Tốn công nhưng giữ ranh giới rõ. |

**Đây là phân loại thiết kế mang tính định hướng**, không phải phép đo có tính thống kê hay một bảo đảm về tính tương thích của từng phiên bản.

### 23.1. Phương pháp chấm điểm 5 chiều

Để đánh giá dự án, có thể cho từng chiều từ 0 đến 2:

- **0:** dùng API/kiểu dữ liệu phổ thông, đã kiểm chứng.
- **1:** có khác biệt nhỏ, có thể xử lý trong adapter.
- **2:** phụ thuộc sâu vào tính năng DBMS/provider.

Năm chiều:

1. **Signature:** IN/OUT/INOUT/cursor/types.
2. **Result shape:** số result sets, update counts, mapping.
3. **Transaction:** rollback, concurrency, internal COMMIT.
4. **Dialect:** body SQL, function/procedure semantics.
5. **Operations:** migration, permissions, versions, error codes.

Ví dụ chấm thử:

| Chiều | Procedure giữ kho tối giản | Procedure báo cáo nhiều cursor |
| --- | ---: | ---: |
| Signature | 1 | 2 |
| Result shape | 0 | 2 |
| Transaction | 1 | 1 |
| Dialect | 2 | 2 |
| Operations | 1 | 2 |
| **Tổng** | **5/10** | **9/10** |

Con số trên là **ví dụ của một rubric nội bộ**, không phải tiêu chuẩn JPA. Nó hữu ích để thảo luận mức đầu tư adapter/tests. Không nên dùng một ngưỡng điểm cơ học để quyết định sản phẩm có thể chạy trên mọi database.

## 24. Xác định portability requirement trước khi viết code

Một nhóm nên trả lời rõ:

1. Hiện tại sản phẩm chỉ chạy trên một DBMS hay phải hỗ trợ nhiều DBMS?
2. Cần đổi JPA provider nhưng giữ DBMS, hay cần đổi cả DBMS?
3. Có phiên bản database/driver/provider cụ thể nào phải hỗ trợ?
4. Routine có thể được viết lại theo từng DBMS không?
5. Hợp đồng ứng dụng cần giữ nguyên những gì: status, dữ liệu, transaction, ordering, error?
6. Có cần giữ một SQL script duy nhất hay chấp nhận migrations riêng?
7. Những tính năng vendor-specific có lý do hiệu năng/pháp lý nào không thể bỏ?
8. Có đủ hạ tầng integration tests trên tất cả DBMS mục tiêu không?
9. Dữ liệu lớn, N+1 hoặc streaming có phải yêu cầu bắt buộc không?
10. Đổi DBMS là khả năng lý thuyết hay kế hoạch sản phẩm với thời hạn cụ thể?

Nếu sản phẩm **không có yêu cầu hỗ trợ DBMS thứ hai**, việc viết nhiều adapters có thể làm tăng chi phí không cần thiết. Tuy vậy, vẫn nên giữ **hợp đồng nghiệp vụ tách khỏi chi tiết procedure** để giảm lock-in ở tầng ứng dụng.

## 25. Bộ kiểm thử hợp đồng cho lời gọi thủ tục

Khả chuyển không thể được xác nhận chỉ bằng việc code Java biên dịch. Cần kiểm thử với **JPA provider + JDBC driver + DBMS thật**.

### 25.1. Những ca kiểm thử bắt buộc cho reserve_stock

| Ca kiểm thử | Input / trạng thái | Kết quả kỳ vọng |
| --- | --- | --- |
| Giữ hàng thành công | Tồn 12, giữ 5 | OUT RESERVED; tồn khả dụng 7, reserved tăng 5. |
| Không đủ hàng | Tồn 4, giữ 5 | OUT INSUFFICIENT_STOCK; dữ liệu không đổi. |
| Sản phẩm không tồn tại | ID không có | OUT PRODUCT_NOT_FOUND; không thêm dữ liệu sai. |
| Số lượng không hợp lệ | 0 hoặc âm | INVALID_QUANTITY; không sửa bảng. |
| Giữ đúng toàn bộ số lượng | Tồn 5, giữ 5 | Thành công; tồn khả dụng 0, không âm. |
| Gọi lần nữa | Tồn đã 0, giữ 5 | Từ chối; không trừ âm. |
| Hai request đồng thời | Cùng một product, cùng tranh tồn | Tổng lượng giữ không vượt tồn ban đầu. |
| Rollback sau khi procedure trả thành công | Có transaction rollback chủ động | Trạng thái dữ liệu quay lại như trước. |
| Caller thiếu quyền | Role không có EXECUTE | Nhận lỗi phù hợp, không làm dữ liệu thay đổi. |
| OUT parameter null/bất thường | Routine lỗi hoặc lệch contract | Adapter phát hiện lỗi rõ, không trả success. |
| Đổi driver/provider | Cùng contract | Signature, OUT, transaction behavior không đổi. |
| Có pending changes trong persistence context | Sửa dữ liệu rồi call | Luồng flush/visibility được xác nhận. |
| Managed entity đã tải trước call | Procedure update bảng | Luồng refresh/reload không dùng stale state. |

### 25.2. Kiểm tra với nhiều DBMS

Một ma trận test:

```text
Contract suite
    |
    +-- PostgreSQL adapter
    |      +-- PostgreSQL version X
    |      +-- JDBC driver Y
    |      +-- JPA provider Z
    |
    +-- SQL Server adapter
    |      +-- SQL Server version A
    |      +-- JDBC driver B
    |      +-- JPA provider Z
    |
    +-- Oracle adapter (nếu được hỗ trợ)
           +-- Oracle version M
           +-- JDBC driver N
           +-- JPA provider Z
```

Tên X/Y/Z là placeholders cần được điền bằng **versions thực tế**. Nếu thay JPA provider, phải bổ sung thêm biến thể provider vào ma trận.

### 25.3. Vì sao mock không đủ?

Một unit test mock `StoredProcedureQuery` có thể xác nhận:

```java
sp.setParameter(1, productId);
sp.setParameter(2, quantity);
```

được gọi đúng. Nhưng mock không xác nhận được:

- Procedure có tồn tại trong schema không.
- Driver nhận named/positional OUT không.
- Type conversion có đúng không.
- Result sets/update counts thực sự xuất hiện thế nào.
- Transaction có rollback được không.
- Hai request đồng thời có gây tồn âm không.
- Cú pháp procedure/migration có chạy trên DBMS đích không.

**Integration test là điều kiện bắt buộc nếu hệ thống tuyên bố hỗ trợ một combo DBMS/driver/provider cụ thể.**

### 25.4. Testcontainers hoặc database test environment

Trong những dự án phù hợp, có thể dùng Testcontainers để khởi chạy DBMS cho integration tests; nhưng phải chú ý:

- Một số DBMS cần license/configuration đặc biệt.
- Container image/version phải gần production.
- Cần cài migration trước khi chạy test.
- Test nên tạo dữ liệu độc lập và dọn dẹp đúng.
- Concurrency test cần đồng bộ hai transactions thật, không giả lập tuần tự.
- Không nên coi database in-memory khác vendor là bằng chứng hỗ trợ vendor đó.

Bài này chỉ trình bày **thiết kế kiểm thử**, không thực thi test.

## 26. Kiểm thử nhiều result sets và REF_CURSOR

Với những routine trả dữ liệu phức tạp, cần thêm các tình huống:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Result set đầu tiên rỗng | Vẫn đọc được phần tiếp theo. |
| Update count 0 | Không nhầm với kết thúc. |
| Update count xen giữa hai result sets | Vòng lặp không dừng sớm. |
| NOCOUNT ON/OFF ở SQL Server | Không suy sai nghiệp vụ từ counts. |
| OUT parameter sau result sets | Có thể đọc sau khi duyệt. |
| REF_CURSOR output | Driver/provider đọc được đúng kiểu, đúng transaction. |
| Thay đổi column alias | Mapping phát hiện incompatibility. |
| BIGINT/DECIMAL/TIMESTAMP | Kiểu và precision đúng. |
| Nhiều result sets khác schema | Ánh xạ đúng từng tập theo contract. |
| Fetch nhiều hàng | Memory/time/resource usage nằm trong giới hạn. |

Một câu hỏi kiểm thử tốt không chỉ là “`getResultList()` trả bao nhiêu rows?”, mà còn là **“đây là result set thứ mấy, thuộc contract nào và có bị một update count đứng trước không?”**

## 27. Khi nào cần quay về JDBC CallableStatement?

Nếu `StoredProcedureQuery` không đáp ứng một tính năng vendor cụ thể, JDBC `CallableStatement` cho quyền kiểm soát thấp hơn:

```java
try (CallableStatement statement =
        connection.prepareCall("{call reserve_stock(?, ?, ?)}")) {

    statement.setLong(1, productId);
    statement.setInt(2, quantity);
    statement.registerOutParameter(3, java.sql.Types.INTEGER);

    boolean isResultSet = statement.execute();

    while (true) {
        if (isResultSet) {
            try (ResultSet rs = statement.getResultSet()) {
                while (rs.next()) {
                    // Đọc rows hiện tại.
                }
            }
        } else {
            int count = statement.getUpdateCount();
            if (count == -1) {
                break;
            }
        }

        isResultSet = statement.getMoreResults();
    }

    int status = statement.getInt(3);
    if (statement.wasNull()) {
        throw new IllegalStateException("Missing OUT status");
    }
}
```

Đoạn code dùng `java.sql.CallableStatement`, `java.sql.ResultSet` và connection đã được cung cấp. Call escape syntax `{call ...}` và việc driver hỗ trợ routine signature vẫn phải được kiểm tra.

### 27.1. Chuyển sang JDBC không tự tăng khả chuyển

JDBC `CallableStatement` cũng đi qua **driver và DBMS**. Nó giúp kiểm soát nhiều chi tiết mà JPA che đi, nhưng:

- Vendor-specific SQL types vẫn tồn tại.
- Named parameter support vẫn khác nhau.
- Functions/procedures vẫn khác.
- Transaction và isolation vẫn phụ thuộc DBMS.
- Driver-specific extensions có thể tạo phụ thuộc mới.

Vì thế JDBC là một **lựa chọn kỹ thuật khi cần năng lực thấp hơn**, không phải giải pháp tự động biến stored procedures thành portable.

### 27.2. Kết hợp JDBC và JPA transaction

Nếu JPA đang quản lý transaction, không mở connection hoàn toàn độc lập rồi mặc định rằng JDBC query sẽ tham gia cùng transaction.

Trong Spring, nên dùng `DataSource`/`JdbcTemplate` được cấu hình đồng bộ với transaction manager phù hợp. Với Hibernate-specific access, có thể dùng connection callback theo provider, nhưng đó là một lựa chọn **giảm tính provider portability**.

Đưa các chi tiết đó vào adapter để domain không phụ thuộc vào cách lấy connection.

## 28. Những trade-off khi tối ưu hiệu năng

Stored procedure thường được chọn vì lý do hiệu năng. Nhưng cần phân biệt:

- **Giảm round-trip:** gom nhiều statements vào một call có thể giảm số lần giao tiếp app–DB.
- **Giảm dữ liệu truyền:** procedure chỉ trả summary có thể hiệu quả hơn tải hàng nghìn entities.
- **Tận dụng thuật toán DBMS:** dùng locking/window functions/temporary table/partition-specific logic.
- **Tăng coupling:** logic gắn với ngôn ngữ DBMS và kế hoạch triển khai routine.
- **Tăng chi phí test:** cần xác nhận output, transaction và driver behavior trên mọi DBMS mục tiêu.

### 28.1. Tối ưu phải đo

Một use case xử lý 1 triệu rows có thể phù hợp với SQL server-side thay vì lặp qua entity JPA. Nhưng quyết định nên dựa trên:

- Tổng thời gian thực thi.
- Số round-trips.
- Số hàng đọc/ghi.
- Transaction lock duration.
- Memory app và DB.
- Query plan và index.
- Tải đồng thời.
- Chi phí triển khai/rollback migration.

Nếu một stored procedure nhanh hơn 30% ở một DBMS nhưng phải viết lại cho ba DBMS khác, nhóm phải quyết định hiệu năng hay khả chuyển là ưu tiên sản phẩm.

### 28.2. “Vendor lock-in” không luôn là lỗi thiết kế

Phụ thuộc vào một tính năng đặc thù có thể là quyết định đúng nếu:

- Chỉ hỗ trợ chính thức một DBMS.
- Tính năng đó giải quyết nút thắt được đo rõ.
- Chi phí chuyển DBMS được chấp nhận và ghi nhận.
- Interface nghiệp vụ được giữ ổn định.
- Có migration, documentation và integration tests.

Vấn đề không phải là **không bao giờ dùng vendor-specific procedures**, mà là **không được đánh giá sai mức phụ thuộc của chúng**.

## 29. Giảm rủi ro bằng những nguyên tắc thiết kế

Một checklist thiết kế tốt:

1. **Đặt domain contract trước**: input, output, status/error, transaction, concurrency invariant.
2. **Giữ parameter types đơn giản** nếu không cần native types.
3. **Hạn chế result sets phức tạp** và tránh phụ thuộc update counts không có ý nghĩa nghiệp vụ.
4. **Ưu tiên OUT/DTO contract rõ** khi cần số liệu hay trạng thái cụ thể.
5. **Để ứng dụng sở hữu transaction** khi kiến trúc yêu cầu atomicity chung với JPA operations.
6. **Cô lập routine names, parameter registration và vendor error codes** trong adapters.
7. **Viết migration riêng theo DBMS** thay vì giả định procedural SQL chung.
8. **Đánh dấu tính năng rủi ro cao**: REF_CURSOR, UDT, JSON native, arrays, function-return-table, dynamic SQL, transaction control.
9. **Test đúng provider + driver + DBMS versions** mà sản phẩm tuyên bố hỗ trợ.
10. **Thiết kế rollback/versioning** khi schema routine thay đổi.
11. **Theo dõi performance và security** sau khi triển khai.
12. **Không dùng JPA API compatibility làm bằng chứng duy nhất** về behavioral portability.

## 30. Các sai lầm thường gặp

### Lỗi 1 — “Dùng StoredProcedureQuery thì procedure chạy trên mọi database”

Sai. API Java là chuẩn, nhưng thân thủ tục, signature và driver behavior vẫn có thể vendor-specific.

### Lỗi 2 — “SQL stored procedure là SQL chuẩn”

Nhiều ngôn ngữ procedural là extension của DBMS: PL/SQL, T-SQL, PL/pgSQL. Một migration thường không chạy nguyên văn trên mọi hệ.

### Lỗi 3 — “Named parameter luôn portable hơn positional parameter”

Không tuyệt đối. Named registration có thể phụ thuộc metadata/naming/provider; positional phụ thuộc signature order. Chọn dựa trên combo được hỗ trợ và contract.

### Lỗi 4 — “OUT Integer phải luôn trả đúng Integer”

Thường có thể, nhưng conversion/nullability/driver support vẫn phải kiểm tra. Với kiểu khác, cần xử lý có chủ đích.

### Lỗi 5 — “Function và procedure thay thế nhau bằng StoredProcedureQuery”

Không luôn đúng. Function trả bảng/scalar có thể cần native SELECT hoặc một cách gọi khác theo DBMS.

### Lỗi 6 — “REF_CURSOR có trong ParameterMode nên chạy mọi nơi”

Sai. Đây là vùng rủi ro cao về DBMS/provider/driver.

### Lỗi 7 — “execute() == false là procedure lỗi”

Sai. Boolean mô tả loại kết quả đầu tiên, không phải trạng thái thành công của nghiệp vụ.

### Lỗi 8 — “hasMoreResults() == false nghĩa là đã hết”

Sai. Phần tiếp theo có thể là update count; kiểm tra `getUpdateCount()`.

### Lỗi 9 — “Update count 0 là hết kết quả”

Sai. `0` là count hợp lệ; `-1` mới là sentinel không có count hiện tại trong luồng duyệt.

### Lỗi 10 — “Cộng mọi update count ra affected business rows”

Sai nếu routine cập nhật nhiều bảng hoặc nhiều mục đích.

### Lỗi 11 — “@SqlResultSetMapping bảo đảm mọi alias/cột được trả đúng”

Không. Mapping vẫn phụ thuộc result shape và conversion từ DBMS.

### Lỗi 12 — “Truyền null giống như bỏ một tham số có default”

Không được mặc định. Null và omitted argument có thể mang nghĩa khác.

### Lỗi 13 — “JPA flush là commit”

Sai. Flush đồng bộ SQL trong transaction; commit mới hoàn tất persistence transaction.

### Lỗi 14 — “Procedure update dữ liệu thì managed entities tự refresh”

Không. Persistence context có thể stale, cần refresh/reload có chủ đích.

### Lỗi 15 — “Procedure OUT success đã chứng minh transaction committed”

Không. Commit vẫn có thể thất bại/rollback sau đó.

### Lỗi 16 — “Một mock test chứng minh multi-DB compatibility”

Không. Mock không kiểm tra driver, syntax, type conversion, locking và transaction DBMS.

### Lỗi 17 — “JDBC CallableStatement giải quyết triệt để vendor lock-in”

Không. JDBC cũng chịu ảnh hưởng DBMS/driver; có thể cần nhiều vendor adapters.

### Lỗi 18 — “Stored procedure tự bảo vệ SQL injection”

Không. SQL động trong thân routine có thể vẫn bị injection.

### Lỗi 19 — “Tên procedure không cần phân biệt schema/package”

Có thể sai. Search path, package owner và quoting có thể đổi routine được gọi.

### Lỗi 20 — “Cứ chuyển hệ quản trị rồi chạy lại tất cả migration là đủ”

Không. Còn business semantics, concurrency, error code, timezone, result sets và vận hành.

### Lỗi 21 — “Bất kỳ routine nào cũng nên chuyển thành Java để portable”

Không luôn đúng. Có những tác vụ bulk/atomic DB logic mà chuyển lên app gây chi phí và rủi ro lớn hơn. Cần đánh đổi có cơ sở.

### Lỗi 22 — “Một adapter đủ cho mọi provider/driver version”

Không bảo đảm. Nếu hành vi driver thay đổi, có thể cần sửa adapter hoặc nâng contract/tests.

## 31. Bài tập thực hành

### Bài 1 — Phân loại tính khả chuyển

Một ứng dụng dùng:

```java
em.createStoredProcedureQuery("dbo.usp_close_month");
```

Thủ tục viết bằng T-SQL với bảng tạm và `TRY...CATCH`.

**Câu hỏi:** Lời gọi này portable ở mức nào?

**Gợi ý đáp án:** `createStoredProcedureQuery` là API chuẩn JPA. Nhưng `dbo`, T-SQL, bảng tạm và exception handling là phụ thuộc SQL Server; muốn chuyển DBMS khác phải viết lại routine và kiểm chứng hành vi.

### Bài 2 — Named hay positional parameters?

Hai DBMS dùng tên tham số `p_order_id` và `@OrderId` nhưng cùng thứ tự signature.

**Gợi ý:** Positional registration có thể giúp Java adapter chung hơn, nhưng cần giữ thứ tự signature đúng. Nếu mỗi DBMS có thứ tự riêng, hãy dùng adapter riêng thay vì ép một convention sai.

### Bài 3 — Procedure trả OUT Integer

Java đăng ký:

```java
sp.registerStoredProcedureParameter(
    3, Integer.class, ParameterMode.OUT
);
```

Routine trên DBMS khác lại trả text `"OK"`.

**Giải thích:** Đây là breaking change của contract. Không chữa bằng cast bừa; cần thống nhất output hoặc adapter chuyển từ vendor representation sang domain status.

### Bài 4 — Nhiều result sets

Một procedure trả:

```text
RESULT_SET orders
UPDATE_COUNT(0)
RESULT_SET audits
```

**Câu hỏi:** Vì sao `while (sp.hasMoreResults())` sai?

**Đáp án:** `hasMoreResults()` trả false khi phần kế tiếp là update count dù sau đó còn result set. Cần đọc `getUpdateCount()` và tiếp tục.

### Bài 5 — OUT parameter và transaction

Procedure trả `status = RESERVED` nhưng transaction sau đó rollback.

**Đáp án:** Không được coi hàng đã được giữ bền vững. Tầng nghiệp vụ phải coi commit thành công là điều kiện hoàn tất.

### Bài 6 — Bulk UUID

Một procedure nhận mảng 20.000 UUID theo SQL Server table-valued parameter. Hệ thống cần chuyển PostgreSQL.

**Gợi ý:** Đánh giá rủi ro cao. Có thể viết hai adapters, dùng staging table chung theo batch ID hoặc tận dụng vendor-specific array/TVP riêng cho từng DBMS; test type conversion và giới hạn kích thước.

### Bài 7 — PostgreSQL function trả bảng

Một routine PostgreSQL được gọi:

```sql
SELECT * FROM find_paid_orders(101);
```

**Câu hỏi:** Có bắt buộc gọi qua `StoredProcedureQuery` để “đúng JPA” không?

**Đáp án:** Không. Có thể dùng native query/DTO mapping. Function trả bảng không nhất thiết có cách gọi portable giống procedure OUT hoặc SQL Server SELECT result sets.

### Bài 8 — Error code

Adapter SQL Server kiểm tra một mã lỗi vendor cụ thể để nhận biết unique violation.

**Gợi ý:** Đặt việc chuyển lỗi vào SQL Server adapter. Domain chỉ biết `DuplicateReservation` hoặc kết quả nghiệp vụ tương đương, không phụ thuộc mã lỗi SQL Server.

### Bài 9 — Transaction concurrent

Hai người cùng giữ hàng từ tồn 5, mỗi người giữ 4.

**Câu hỏi:** Chỉ kiểm tra hai lần gọi Java trả status đúng đã đủ không?

**Đáp án:** Không. Phải test đồng thời thật để xác nhận available không âm và chỉ một reservation thành công theo inventory invariant.

### Bài 10 — REF_CURSOR

Một thủ tục Oracle trả hai OUT cursors; đội dự án định chuyển SQL Server.

**Gợi ý:** Không coi `ParameterMode.REF_CURSOR` là hợp đồng portable tự nhiên. Có thể định nghĩa hai DTO lists trong application port và triển khai retrieval tương ứng trong từng DBMS adapter.

### Bài 11 — Mapping constructor

Query đặt `@ColumnResult(name="total_amount", type=BigDecimal.class)`, nhưng routine mới trả alias `amount_total`.

**Giải thích:** Java metadata chuẩn vẫn biên dịch nhưng runtime result mapping có thể thất bại. Đây là behavioral/schema contract break; cần migration và integration test.

### Bài 12 — NOC0UNT và update count

SQL Server procedure bật `SET NOCOUNT ON`; ứng dụng không nhận được counts như trước.

**Đáp án:** Điều này không chứng minh UPDATE không xảy ra. Số liệu nghiệp vụ cần OUT/status result set có hợp đồng rõ, không dựa vào row-count message phụ trợ.

### Bài 13 — Giảm phụ thuộc với adapter

Yêu cầu domain là:

```java
ReservationOutcome reserve(long productId, int quantity);
```

Một DBMS dùng OUT Integer; DBMS khác dùng function trả String.

**Gợi ý:** Viết hai adapters chuyển về cùng `ReservationOutcome`. Service không thay đổi theo dialect.

### Bài 14 — Có nên dùng procedure?

Use case chỉ lấy tên và giá của 20 sản phẩm cho một trang catalog.

**Gợi ý:** JPQL/Criteria với DTO projection thường khả chuyển và dễ bảo trì hơn một procedure báo cáo riêng chỉ để SELECT hai cột.

### Bài 15 — Portability risk review

Một routine có: three IN params, REF_CURSOR OUT, một `JSONB` OUT, hai SELECT debug và COMMIT nội bộ.

**Gợi ý:** Rủi ro cao ở signature/result shape/dialect/transaction. Giảm rủi ro bằng việc tách contract, bỏ SELECT debug khỏi API, trả DTO/status rõ và để transaction manager điều phối khi khả thi.

## 32. Câu hỏi tự kiểm tra

**1. Vì sao `StoredProcedureQuery` có tính chuẩn nhưng stored procedure không hoàn toàn portable?**

Vì JPA chuẩn hóa API gọi, còn ngôn ngữ định nghĩa routine, data types, cursor, transaction và cách driver trả kết quả không được thống nhất toàn bộ giữa DBMS.

**2. Có những tầng kỹ thuật nào cần xét khi đánh giá?**

Application/domain, Jakarta Persistence API, JPA provider/dialect, JDBC driver và DBMS.

**3. `ParameterMode` có những giá trị nào?**

`IN`, `OUT`, `INOUT` và `REF_CURSOR`.

**4. Named parameter có luôn tốt hơn positional parameter không?**

Không. Named phụ thuộc vào naming/driver/provider; positional phụ thuộc thứ tự signature.

**5. Truyền null và bỏ một parameter có default có luôn giống nhau không?**

Không.

**6. Có thể coi function trả bảng và procedure trả result set là một dạng chung tuyệt đối không?**

Không. Các DBMS có cú pháp và semantics khác nhau; có thể cần native SELECT hoặc adapters riêng.

**7. Vì sao REF_CURSOR thuộc nhóm rủi ro cao?**

Vì hỗ trợ cursor, cách đăng ký, lifecycle và cách đọc phụ thuộc DBMS/provider/driver.

**8. `execute() == false` có nghĩa procedure thất bại không?**

Không. Nó nói kết quả đầu tiên không phải result set.

**9. `hasMoreResults() == false` có chứng minh đã hết không?**

Không. Có thể là update count; cần kiểm tra `getUpdateCount()`.

**10. Update count `0` khác `-1` thế nào?**

0 là số dòng ảnh hưởng hợp lệ; -1 biểu thị không có update count hiện tại trong luồng duyệt.

**11. OUT status code và update count có giống nhau không?**

Không. OUT do contract nghiệp vụ quy định; update count phản ánh phần DML mà driver phơi bày.

**12. @NamedStoredProcedureQuery có làm SQL thân thủ tục portable không?**

Không. Nó chuẩn hóa metadata Java.

**13. Có thể giữ cùng Java domain interface dù mỗi DBMS cần routine riêng không?**

Có. Dùng Port–Adapter và mapping kết quả về DTO/domain outcome chung.

**14. Nếu procedure cập nhật bảng, managed entity đã tải có tự refresh không?**

Không được giả định. Cần xử lý trạng thái stale có chủ đích.

**15. Flush có đồng nghĩa commit không?**

Không. Flush đồng bộ SQL trong transaction, chưa hoàn tất transaction.

**16. Vì sao cần test concurrency khi chuyển DBMS?**

Vì isolation, locking và atomicity có thể khác nhau, dẫn tới lost update hoặc dữ liệu âm dù Java code giống nhau.

**17. Chỉ unit test mock là đủ để chứng minh multi-DB portability không?**

Không. Cần integration tests trên DBMS/driver/provider thực tế.

**18. Chuyển sang JDBC có tự giải quyết phụ thuộc vendor không?**

Không. JDBC cho nhiều quyền kiểm soát hơn nhưng vẫn chịu phụ thuộc DBMS/driver.

**19. Vì sao nên dùng DTO cho nhiều result sets báo cáo?**

Để có contract rõ và tránh phụ thuộc vào việc ánh xạ thiếu cột thành managed entity.

**20. Lỗi vendor-specific nên được xử lý ở tầng nào?**

Ở adapter/infrastructure rồi chuyển sang domain errors hoặc status thống nhất.

**21. “Portable giữa các DBMS” cần nêu thêm điều gì?**

Những DBMS versions, JDBC drivers, JPA providers, routine signatures và behavior được kiểm chứng.

**22. Vì sao cần version routine contract?**

Để kiểm soát breaking changes của tham số, result set, status codes và transaction semantics qua migration/rolling deployment.

**23. Dùng stored procedure trong một sản phẩm chỉ hỗ trợ một DBMS có luôn sai không?**

Không. Có thể là trade-off hợp lý nếu hiệu năng/tính năng yêu cầu và phụ thuộc được quản lý rõ.

**24. Khi nào nên ưu tiên JPQL/Criteria?**

Khi yêu cầu có thể biểu diễn tốt bằng query/CRUD phổ thông và khả chuyển là ưu tiên.

**25. Định nghĩa ngắn gọn nhất của tính khả chuyển lời gọi thủ tục?**

**Ứng dụng giữ được cùng contract nghiệp vụ khi thay provider/driver/DBMS mục tiêu, với mức thay đổi đã được xác định và kiểm chứng.** Dùng API chuẩn là một bước, không phải toàn bộ điều kiện.

## 33. Ghi nhớ cuối bài

**Khả chuyển của lời gọi stored procedure là một bài toán nhiều tầng.** `StoredProcedureQuery`, `@NamedStoredProcedureQuery`, `ParameterMode` và `@SqlResultSetMapping` cung cấp một giao diện JPA chuẩn, nhưng **thủ tục không trở thành SQL portable** chỉ vì được gọi qua giao diện đó.

Những giới hạn quan trọng nhất cần nhận diện:

- **Ngôn ngữ thủ tục và cách gọi routine** khác nhau giữa DBMS; function không luôn giống procedure.
- **OUT/INOUT, REF_CURSOR, named/positional parameters và kiểu SQL đặc thù** có mức hỗ trợ khác nhau theo provider/driver.
- **Nhiều result sets, update counts và thứ tự kết quả** cần xử lý theo cơ chế duyệt đúng và được kiểm chứng trên database thật.
- **Transaction, flush, stale persistence context, locking và concurrency** có thể làm hành vi khác nhau dù Java code giống nhau.
- **Result mappings, error codes, schema names và quyền EXECUTE** đều là thành phần của hợp đồng tích hợp.
- **Port–Adapter, status/DTO contract rõ, migrations riêng theo DBMS và integration tests nhiều nền tảng** là các cách giảm phụ thuộc có kiểm soát.

Một thiết kế tốt không cần hứa “chuyển DBMS mà không phải sửa một dòng nào”. Nó phải **nói rõ phần nào là chuẩn JPA, phần nào đặc thù nhà cung cấp, và phần nào phải được kiểm thử lại khi chuyển hệ quản trị**. Nếu thực hiện được điều đó, ứng dụng có thể tận dụng sức mạnh stored procedure mà vẫn giữ được ranh giới kiến trúc rõ ràng, giảm rủi ro lock-in và bảo toàn hành vi nghiệp vụ khi môi trường thay đổi.
