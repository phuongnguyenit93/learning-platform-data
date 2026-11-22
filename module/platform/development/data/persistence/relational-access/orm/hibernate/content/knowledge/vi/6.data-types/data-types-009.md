# Kiểu tùy chỉnh với UserType hoặc SPI kiểu dữ liệu khi converter chưa đủ

## 1. Bối cảnh: khi kiểu Java và kiểu SQL không còn khớp một cách đơn giản

Trong Java, một thuộc tính entity thường dùng `String`, `Long`, `BigDecimal`, `LocalDate`, `UUID` hoặc enum. Jakarta Persistence (JPA) và Hibernate ORM đã có cách ánh xạ các kiểu phổ biến này sang cột trong cơ sở dữ liệu quan hệ. Tuy nhiên, các ứng dụng thực tế còn dùng **value object** do đội phát triển định nghĩa hoặc loại cột riêng của một hệ quản trị cơ sở dữ liệu:

- `ProductCode` là mã sản phẩm được kiểm tra định dạng thay vì một chuỗi bất kỳ.
- `Money` lưu số tiền và loại tiền, có thể cần nhiều cột.
- `InetNetwork` lưu địa chỉ IP và prefix vào cột PostgreSQL `inet`.
- `Map<String, Object>` hoặc POJO được lưu dưới dạng JSON/JSONB.
- Kiểu SQL đặc thù như range, geometry hoặc định dạng binary có giao thức JDBC riêng.

Vấn đề không chỉ là chuyển dữ liệu thành một chuỗi. Hibernate còn phải chọn mã JDBC type, cách bind vào `PreparedStatement`, cách đọc `ResultSet`, cách so sánh giá trị để dirty checking, cách tạo snapshot và xử lý cache.

Bài học này trình bày cách chọn mức mở rộng phù hợp, từ converter chuẩn đến `UserType<T>` và các SPI kiểu dữ liệu của Hibernate. Ví dụ chính sử dụng PostgreSQL `inet` vì nó cho thấy rõ tại sao **trả về `String` từ converter chưa chắc giúp JDBC bind đúng kiểu của database**.

> **Phạm vi:** Ví dụ triển khai `UserType<T>` dựa trên Hibernate ORM **6.x**, Jakarta Persistence (`jakarta.persistence.*`) và Java 17+. Hibernate 5.x dùng các chữ ký method và cách tổ chức type khác; luôn đối chiếu API với phiên bản đang sử dụng.

Sau bài học, bạn cần phân biệt được: chuyển đổi giá trị, ánh xạ một hay nhiều cột, lựa chọn JDBC binder/extractor, kế hoạch mutability, registration và rủi ro khi phụ thuộc vào một provider cụ thể.

## 2. Mô hình các tầng ánh xạ kiểu

Sơ đồ khái niệm khi Hibernate ghi hoặc đọc một thuộc tính:

~~~text
     Domain object trong Java
          InetNetwork
               |
          JavaType<T>
  equals / hash / wrap / unwrap
        MutabilityPlan
               |
         Basic mapping
               |
           JdbcType
      binder / extractor
               |
  PreparedStatement / ResultSet
               |
          JDBC driver
               |
       PostgreSQL inet
~~~

Các khái niệm có nhiệm vụ khác nhau:

| Thành phần | Nguồn API | Trách nhiệm chính |
|---|---|---|
| `AttributeConverter<X, Y>` | Jakarta Persistence | Chuyển giá trị Java kiểu X sang kiểu cột Y và ngược lại |
| `@Embedded` / `@Embeddable` | Jakarta Persistence | Gom nhiều thuộc tính vào đối tượng giá trị, thường lưu nhiều cột |
| `UserType<T>` | Hibernate | Mô tả basic mapping, trực tiếp điều khiển JDBC đọc/ghi và ngữ nghĩa giá trị |
| `JavaType<T>` | Hibernate SPI | Mô tả kiểu Java: equality, wrap/unwrap, mutability |
| `JdbcType` | Hibernate SPI | Mô tả loại JDBC và cơ chế bind/extract |
| `BasicType<T>` | Hibernate SPI | Kết hợp mô tả Java type và JDBC type |
| `MutabilityPlan<T>` | Hibernate SPI | Quy định deep copy và tách/khôi phục giá trị |
| `@JdbcTypeCode` | Hibernate | Chọn JDBC type code được Hibernate hỗ trợ |

**Kiểu Java**, **loại JDBC** và **tên kiểu cột SQL** là ba khái niệm có liên hệ nhưng không đồng nhất. Ví dụ, `InetNetwork` là lớp Java; `Types.OTHER` là JDBC type code có thể dùng; còn `inet` là kiểu cột của PostgreSQL.

Một thiết kế custom type tốt cần làm rõ trách nhiệm nào đã được Hibernate hỗ trợ và trách nhiệm nào thực sự phải viết thêm.

## 3. Điểm xuất phát: AttributeConverter của Jakarta Persistence

Giả sử muốn tránh truyền mã sản phẩm như chuỗi tùy ý:

~~~java
package example.types;

import java.io.Serializable;

public record ProductCode(String value) implements Serializable {
    public ProductCode {
        if (value == null || !value.matches("[A-Z0-9-]{4,30}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}
~~~

Cơ sở dữ liệu chỉ cần `VARCHAR(30)`. Một converter chuẩn thường là đủ:

~~~java
package example.types;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class ProductCodeConverter
        implements AttributeConverter<ProductCode, String> {

    @Override
    public String convertToDatabaseColumn(ProductCode code) {
        return code == null ? null : code.value();
    }

    @Override
    public ProductCode convertToEntityAttribute(String stored) {
        return stored == null ? null : new ProductCode(stored);
    }
}
~~~

Áp dụng trong entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue
    private Long id;

    @Convert(converter = ProductCodeConverter.class)
    @Column(name = "product_code", nullable = false, unique = true, length = 30)
    private ProductCode code;

    protected Product() {}
}
~~~

Converter chuyển đổi dữ liệu giá trị, còn Hibernate tiếp tục dùng JDBC mapping dành cho `String`. Domain model không phải biết cách gọi `PreparedStatement.setString`.

Một vài đặc điểm:

- `X` là kiểu domain (`ProductCode`), `Y` là kiểu biểu diễn lưu trữ (`String`).
- `autoApply = true` có thể tự áp dụng converter cho các thuộc tính đủ điều kiện cùng kiểu, nhưng cần cân nhắc phạm vi tác động.
- `@Convert` cho phép khai báo converter tường minh trên thuộc tính, trừ trường hợp bị quy định khác bởi mapping của JPA.
- Converter không thay thế validation, database constraint, schema migration hoặc transaction.
- Một converter của JPA thường thích hợp khi đầu ra của nó là một kiểu basic đã được provider/JDBC hỗ trợ tốt.

### Giới hạn của converter

Interface `AttributeConverter` chỉ có hai phép chuyển đổi:

~~~java
Y convertToDatabaseColumn(X attribute);
X convertToEntityAttribute(Y dbData);
~~~

Nó không cho ứng dụng truy cập trực tiếp `PreparedStatement`, `ResultSet`, JDBC type code, binder/extractor hoặc mutability plan. Nếu converter trả về `String`, Hibernate có thể bind bằng cách thông thường cho `String`; điều này chưa chắc phù hợp với một kiểu database riêng.

Ví dụ: `@Column(columnDefinition = "inet")` có thể giúp sinh DDL cho cột PostgreSQL, nhưng tự nó **không bảo đảm tham số của custom domain type được bind theo giao thức `inet`**. Nếu query ghi một chuỗi được bind theo kiểu `VARCHAR`, PostgreSQL có thể từ chối kiểu dữ liệu tùy vào ngữ cảnh SQL và quy tắc cast.

Converter cũng không phải công cụ chính để trải một object ra nhiều cột: với `Money(amount, currency)` cần hai cột riêng, `@Embeddable` thường hợp lý hơn.

## 4. Chọn công cụ dựa trên yêu cầu

| Nhu cầu ánh xạ | Công cụ nên xét trước | Điểm cần chú ý |
|---|---|---|
| Value object ↔ `VARCHAR`, `INTEGER`, v.v. | `AttributeConverter` | Đầu ra phải là kiểu cột/JDBC mà provider đã hiểu |
| Enum ↔ chuỗi | `@Enumerated(EnumType.STRING)` | Không cần tự viết type cho enum thông thường |
| Value object ↔ nhiều cột | `@Embeddable`, `@AttributeOverride` | Không ép basic mapping một cột quản lý nhiều cột |
| Java object ↔ JSON | `@JdbcTypeCode(SqlTypes.JSON)` nếu được hỗ trợ | Kiểm tra dialect, thư viện serialization và version |
| Java object ↔ loại JDBC/driver đặc thù | `UserType<T>` hoặc `JdbcType` | Cần tự điều khiển bind/extract |
| Kiểu Java mutable cần snapshot riêng | `MutabilityPlan` hoặc custom type phù hợp | Dirty checking và cache phụ thuộc copy/equality |
| Nhiều domain type dùng cùng JDBC protocol | `JavaType` + `JdbcType` | Có thể chia sẻ descriptor thay vì lặp code |
| Một field cần type riêng, ít sử dụng lại | `@Type(CustomUserType.class)` | Chọn phạm vi mapping cục bộ |

Không chọn UserType chỉ vì kiểu Java là lớp tự viết. Khi Hibernate có built-in mapping hoặc converter chuẩn đã xử lý đủ yêu cầu, thêm SPI có thể làm tăng phụ thuộc và khó nâng cấp.

## 5. Ví dụ: ánh xạ PostgreSQL inet bằng UserType

### 5.1. Bài toán và lược đồ

Ứng dụng ghi lại IP client trong sự kiện đăng nhập. PostgreSQL có kiểu `inet` hỗ trợ IPv4/IPv6 và thông tin prefix. Domain chỉ muốn dùng `InetNetwork`, không muốn đưa `PGobject` của PostgreSQL JDBC vào business service.

Ví dụ DDL:

~~~sql
CREATE TABLE login_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    client_address inet NOT NULL,
    note VARCHAR(200)
);

INSERT INTO login_events (client_address, note)
VALUES ('192.0.2.20/32', 'Example login');
~~~

Mục tiêu là bind/extract trực tiếp theo JDBC protocol mà driver PostgreSQL dùng cho `inet`. Trước khi triển khai, hãy kiểm tra Hibernate version/dialect có sẵn mapping mong muốn không; ví dụ sau minh họa cách tự triển khai khi tính năng tích hợp không đáp ứng.

### 5.2. Domain value object bất biến

File `InetNetwork.java`:

~~~java
package example.network;

import java.io.Serializable;

public record InetNetwork(String notation) implements Serializable {

    public InetNetwork {
        if (notation == null || notation.isBlank()) {
            throw new IllegalArgumentException("IP notation is required");
        }
        notation = notation.trim();
    }
}
~~~

Có thể tạo `new InetNetwork("192.0.2.20/32")`. Đối tượng chỉ chuẩn hóa khoảng trắng và kiểm tra rỗng; **chưa phải parser hợp lệ hóa toàn bộ cú pháp địa chỉ IP và prefix**. Trong ứng dụng production, cần validation/canonicalization phù hợp hoặc thư viện địa chỉ mạng có hợp đồng rõ ràng. PostgreSQL sẽ áp đặt quy tắc kiểu `inet` khi ghi.

Dùng record với `String` bất biến giúp đơn giản hóa deep copy và snapshot semantics.

### 5.3. Implement UserType trong Hibernate 6.x

File `PostgresInetUserType.java`:

~~~java
package example.network;

import java.io.Serializable;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Objects;

import org.hibernate.engine.spi.SharedSessionContractImplementor;
import org.hibernate.usertype.UserType;
import org.postgresql.util.PGobject;

public class PostgresInetUserType implements UserType<InetNetwork> {

    @Override
    public int getSqlType() {
        return Types.OTHER;
    }

    @Override
    public Class<InetNetwork> returnedClass() {
        return InetNetwork.class;
    }

    @Override
    public boolean equals(InetNetwork x, InetNetwork y) {
        return Objects.equals(x, y);
    }

    @Override
    public int hashCode(InetNetwork x) {
        return Objects.hashCode(x);
    }

    @Override
    public InetNetwork nullSafeGet(
            ResultSet rs,
            int position,
            SharedSessionContractImplementor session,
            Object owner) throws SQLException {

        String stored = rs.getString(position);
        return stored == null ? null : new InetNetwork(stored);
    }

    @Override
    public void nullSafeSet(
            PreparedStatement st,
            InetNetwork value,
            int index,
            SharedSessionContractImplementor session) throws SQLException {

        if (value == null) {
            st.setNull(index, Types.OTHER);
            return;
        }

        PGobject pgValue = new PGobject();
        pgValue.setType("inet");
        pgValue.setValue(value.notation());
        st.setObject(index, pgValue);
    }

    @Override
    public InetNetwork deepCopy(InetNetwork value) {
        return value; // Immutable
    }

    @Override
    public boolean isMutable() {
        return false;
    }

    @Override
    public Serializable disassemble(InetNetwork value) {
        return value;
    }

    @Override
    public InetNetwork assemble(Serializable cached, Object owner) {
        return (InetNetwork) cached;
    }

    @Override
    public InetNetwork replace(
            InetNetwork detached,
            InetNetwork managed,
            Object owner) {
        return detached;
    }
}
~~~

Code dựa vào dependency Hibernate 6.x và PostgreSQL JDBC driver (artifact phổ biến: `org.postgresql:postgresql`). `UserType<T>` là API riêng của Hibernate, nên type này phụ thuộc version/provider và driver PostgreSQL.

### 5.4. Gắn UserType vào entity

~~~java
package example.network;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Type;

@Entity
@Table(name = "login_events")
public class LoginEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Type(PostgresInetUserType.class)
    @Column(
        name = "client_address",
        nullable = false,
        columnDefinition = "inet"
    )
    private InetNetwork clientAddress;

    @Column(length = 200)
    private String note;

    protected LoginEvent() {}

    public LoginEvent(InetNetwork clientAddress, String note) {
        this.clientAddress = clientAddress;
        this.note = note;
    }

    public Long getId() { return id; }
    public InetNetwork getClientAddress() { return clientAddress; }
    public String getNote() { return note; }
}
~~~

- `@Type(PostgresInetUserType.class)` gắn Hibernate UserType cho thuộc tính Java.
- `@Column(columnDefinition = "inet")` mô tả định nghĩa cột cho DDL; không thay thế `@Type`.
- Constraint `NOT NULL` và kiểu `inet` phải thực sự tồn tại trong schema DB. Khi dùng migration, chỉ đổi annotation không tự sửa bảng đang chạy.
- PostgreSQL driver cần sẵn sàng trong classpath; `PGobject` không phải lớp của JDBC chuẩn.

### 5.5. Lưu và truy vấn

Với `EntityManager` được tạo hợp lệ trong Java SE:

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();
try {
    LoginEvent event = new LoginEvent(
        new InetNetwork("192.0.2.20/32"),
        "Successful login"
    );
    entityManager.persist(event);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
}
~~~

Trong Spring/Jakarta EE có transaction do framework/container quản lý, không tự ý `begin()/commit()` với container-managed entity manager.

Truy vấn JPQL theo tên thuộc tính entity:

~~~java
List<LoginEvent> events = entityManager.createQuery(
        "select e from LoginEvent e where e.clientAddress = :address",
        LoginEvent.class)
    .setParameter("address", new InetNetwork("192.0.2.20/32"))
    .getResultList();
~~~

Trong ngữ cảnh `e.clientAddress`, Hibernate có thể suy luận kiểu tham số từ mapping của thuộc tính và dùng binder tương ứng. Với native SQL hoặc truy vấn mà Hibernate không suy luận được kiểu, cần xét việc khai báo type khi bind theo API Hibernate version thực tế.

**Định nghĩa equality cần nhất quán:** `"192.0.2.20"` và `"192.0.2.20/32"` là hai chuỗi khác nhau trong record, dù về ngữ nghĩa PostgreSQL có thể coi chúng tương đương trong trường hợp thích hợp. Nếu yêu cầu ứng dụng coi chúng giống nhau, cần canonicalize IP/prefix ở tầng value object và định nghĩa equality tương ứng.
## 6. Phân tích hợp đồng UserType

Một custom type cần mô tả cả giá trị Java, đường JDBC và hành vi khi Hibernate so sánh hoặc lưu trạng thái. Đây là lý do UserType có nhiều phương thức hơn converter.

### 6.1. returnedClass và getSqlType

~~~java
@Override
public Class<InetNetwork> returnedClass() {
    return InetNetwork.class;
}

@Override
public int getSqlType() {
    return Types.OTHER;
}
~~~

`returnedClass()` cho biết Java type được ánh xạ. `getSqlType()` là JDBC type code; trong ví dụ PostgreSQL driver xử lý cột `inet` thông qua `Types.OTHER`.

Cần phân biệt `Types.OTHER` với tên SQL `inet`. Type code không tự tạo cột và không đồng nghĩa một kiểu cụ thể của database. Cú pháp DDL thuộc schema, dialect và migration.

### 6.2. nullSafeGet: đường đọc

~~~java
String stored = rs.getString(position);
return stored == null ? null : new InetNetwork(stored);
~~~

`position` của Hibernate 6 là chỉ số cột `ResultSet`, bắt đầu từ 1. Ví dụ `getString()` trả Java null cho SQL NULL. Khi đọc primitive bằng `getInt()` hoặc `getBoolean()`, đôi khi phải gọi `rs.wasNull()` để phân biệt SQL NULL với giá trị mặc định của primitive.

PostgreSQL có thể chuẩn hóa biểu diễn mạng khi lưu hoặc đọc. Nếu muốn equality theo ngữ nghĩa địa chỉ mạng thay vì so sánh literal, cần thiết kế parser/canonicalization riêng, vì việc loại khoảng trắng chưa đảm bảo hai cách biểu diễn tương đương có cùng chuỗi.

### 6.3. nullSafeSet: đường ghi

~~~java
if (value == null) {
    st.setNull(index, Types.OTHER);
} else {
    PGobject pgValue = new PGobject();
    pgValue.setType("inet");
    pgValue.setValue(value.notation());
    st.setObject(index, pgValue);
}
~~~

`index` là chỉ số tham số của `PreparedStatement`, bắt đầu từ 1. `PGobject` cho driver biết cả giá trị lẫn type `inet`. Đây là phần converter không trực tiếp điều khiển được.

Đường ghi gồm SQL INSERT, UPDATE và phép bind tham số dùng trong truy vấn. Một mapping đọc bằng `ResultSet.getString()` thành công chưa chứng minh rằng cách bind tham số cũng tương thích. Nếu truy vấn báo sai kiểu như “column is of type inet but expression is of type character varying”, cần kiểm tra JDBC binder và type inference.

Luôn sử dụng tham số SQL thay vì ghép dữ liệu người dùng vào chuỗi câu lệnh.

### 6.4. equals và hashCode

~~~java
@Override
public boolean equals(InetNetwork x, InetNetwork y) {
    return Objects.equals(x, y);
}

@Override
public int hashCode(InetNetwork x) {
    return Objects.hashCode(x);
}
~~~

Hibernate cần so sánh giá trị cũ và mới khi dirty checking. Hai phương thức phải nhất quán: hai giá trị bằng nhau phải có cùng hash code.

Đối với value object, so sánh bằng tham chiếu `==` thường không đúng. Nhưng so sánh cấu trúc cũng cần cân nhắc ngữ nghĩa: `BigDecimal("1.0")` và `BigDecimal("1.00")` có cùng giá trị số học nhưng `equals()` của BigDecimal phân biệt scale; JSON có thể khác thứ tự key; địa chỉ IPv6 có nhiều ký pháp tương đương. Tùy nghiệp vụ, phải xác định cách chuẩn hóa và so sánh ổn định.

### 6.5. isMutable và deepCopy

~~~java
@Override
public boolean isMutable() {
    return false;
}

@Override
public InetNetwork deepCopy(InetNetwork value) {
    return value;
}
~~~

`InetNetwork` là record chứa `String` bất biến. Trả về cùng tham chiếu là an toàn vì không thể sửa nội dung của object theo API đã thiết kế.

Với kiểu chứa `byte[]` hay `ArrayList` thay đổi được, code tương tự có thể sai:

~~~java
byte[] current = {1, 2, 3};
byte[] snapshot = current; // Chưa tạo bản sao
current[0] = 9;

// snapshot[0] cũng là 9
~~~

Nếu snapshot dùng chung bộ nhớ với giá trị hiện tại, Hibernate có thể bỏ sót thay đổi nội bộ hoặc xử lý cache không đúng. Với mutable type cần deep copy đủ sâu, equality nhất quán và kiểm soát quyền sửa dữ liệu.

### 6.6. disassemble, assemble và replace

~~~java
@Override
public Serializable disassemble(InetNetwork value) {
    return value;
}

@Override
public InetNetwork assemble(Serializable cached, Object owner) {
    return (InetNetwork) cached;
}

@Override
public InetNetwork replace(
        InetNetwork detached,
        InetNetwork managed,
        Object owner) {
    return detached;
}
~~~

`disassemble` cung cấp representation được dùng khi lưu trạng thái cache; `assemble` dựng lại giá trị; `replace` hỗ trợ luồng thay thế/merge giá trị.

Đối với record bất biến và `Serializable`, ví dụ dùng chính object. Với mutable type cần copy thích hợp. Một lớp `Serializable` không tự giải quyết mọi vấn đề second-level cache: định dạng serialization, thay đổi version class, cache phân tán và invalidation vẫn cần được thiết kế riêng.

## 7. Dirty checking, mutability và cache

### 7.1. Thay đổi giá trị của entity được quản lý

Giả sử entity có setter cho địa chỉ mạng:

~~~java
LoginEvent managed = entityManager.find(LoginEvent.class, eventId);
managed.changeAddress(new InetNetwork("198.51.100.25/32"));
~~~

Khi flush, Hibernate phải so sánh thuộc tính hiện tại với snapshot để biết có cần UPDATE. Nếu `UserType.equals` hiểu sai equality hoặc `deepCopy` dùng chung dữ liệu mutable, Hibernate có thể không phát hiện thay đổi hoặc phát sinh update không cần thiết.

Phân biệt thêm:

- **Dirty checking** phát hiện thay đổi trong persistence context.
- **Optimistic locking** với `@Version` phát hiện tranh chấp cập nhật.
- **Database constraint** bảo vệ các quy tắc dữ liệu tại DB.

Một UserType đúng không tự thay thế optimistic locking hay database constraint.

### 7.2. MutabilityPlan của Hibernate 6

Khi sử dụng hệ `JavaType<T>`, `MutabilityPlan<T>` có thể quy định tính bất biến, tạo snapshot, disassemble/assemble. Tách mutability ra khỏi binder giúp cùng quy tắc giá trị được dùng lại qua những JDBC mapping khác nhau.

~~~text
JavaType<CustomValue>
    |
    +-- equality / hash
    |
    +-- MutabilityPlan
    |     +-- isMutable
    |     +-- deepCopy
    |     +-- disassemble / assemble
    |
    +-- wrap / unwrap
~~~

Nếu custom type có nested list, map hoặc byte array, bản sao chỉ có lớp ngoài chưa chắc đủ. Ngược lại, value object bất biến thường đơn giản và đáng tin cậy hơn.

### 7.3. Second-level cache không tự nhiên an toàn

First-level cache gắn với persistence context. Second-level cache là cơ chế tùy chọn để chia sẻ dữ liệu giữa các session trong cấu hình phù hợp. Khi custom type được cache, cần xem:

- Representation lưu cache có thể serialize/deserialize không?
- Có chia sẻ reference mutable với ứng dụng không?
- Giá trị có chứa dữ liệu nhạy cảm hoặc thay đổi thường xuyên không?
- Các hệ thống khác ghi DB trực tiếp có làm cache cũ không?
- Sau nâng cấp phiên bản domain class, dữ liệu cache tồn tại trước đó còn tương thích không?

Không bật cache chỉ vì UserType có method `disassemble`.

## 8. Khi cần nhiều cột: ưu tiên Embeddable

`UserType<T>` cơ bản của Hibernate 6 phục vụ ánh xạ một giá trị qua một JDBC type, không phải giải pháp chung để tách mọi object thành nhiều cột.

Ví dụ `Money` có số tiền và mã đơn vị tiền tệ:

~~~text
Money(100.00, USD)
    |
    +-- total_amount DECIMAL(14,2)
    +-- currency_code VARCHAR(3)
~~~

Mô hình này thích hợp với Jakarta Persistence `@Embeddable`:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.math.BigDecimal;
import java.util.Currency;

@Embeddable
public class Money {

    @Column(name = "total_amount", precision = 14, scale = 2)
    private BigDecimal amount;

    @Column(name = "currency_code", length = 3)
    private String currencyCode;

    protected Money() {}

    public Money(BigDecimal amount, Currency currency) {
        this.amount = amount;
        this.currencyCode = currency.getCurrencyCode();
    }

    public BigDecimal getAmount() { return amount; }

    public Currency getCurrency() {
        return Currency.getInstance(currencyCode);
    }
}
~~~

Dùng trong entity:

~~~java
@Embedded
private Money total;
~~~

Khi cần nhúng cùng lớp ở nhiều vị trí với tên cột khác nhau, dùng `@AttributeOverrides`. Hibernate còn có `CompositeUserType` cho các composite mapping phức tạp; API này đã thay đổi đáng kể giữa Hibernate 5 và 6. Chỉ chọn nó khi các công cụ chuẩn không thể giải quyết mô hình dữ liệu.

Nếu Money thực sự được lưu trong một cột binary hoặc JSON riêng, câu chuyện lại là basic mapping một cột và cần xét converter, built-in mapping hoặc UserType theo JDBC protocol.

## 9. JavaType, JdbcType, BasicType: mở rộng theo thành phần

Một `UserType` viết gọn cho một field có thể đủ. Khi nhiều kiểu Java dùng chung cách bind PostgreSQL, hoặc một kiểu Java được lưu theo nhiều cách JDBC, chia descriptor giúp hạn chế trùng lặp.

### 9.1. JavaType<T>

`JavaType<T>` mô tả phía Java:

- Loại Java được ánh xạ và equality/hash semantics.
- Cách chuyển giá trị sang representation mà JDBC type cần (`unwrap`).
- Cách dựng giá trị Java từ representation đọc được (`wrap`).
- MutabilityPlan và các thông tin giúp Hibernate chọn type.

Một `JavaType<InetNetwork>` có thể biết cách xử lý ký pháp địa chỉ mà không cần biết `PreparedStatement` của PostgreSQL.

### 9.2. JdbcType

`JdbcType` mô tả phía JDBC:

- JDBC type code.
- `ValueBinder`: đưa giá trị lên `PreparedStatement`.
- `ValueExtractor`: lấy giá trị từ `ResultSet`.
- Những thông tin type và SQL khác mà Hibernate/dialect sử dụng.

Một PostgresInetJdbcType có thể đóng gói cách tạo `PGobject(type="inet")`, giúp nhiều domain type tương thích có thể dùng chung binder/extractor.

### 9.3. BasicType<T> và hệ thống registry

~~~text
JavaType<InetNetwork> ----------+
                                 +--> BasicType mapping
JdbcType(PostgreSQL inet) ------+
                                        |
                                 SQL/JDBC/Database
~~~

Hibernate dùng hệ thống `TypeConfiguration` và các registry để chọn, kết hợp và áp dụng descriptors. Cách đăng ký type, thứ tự ưu tiên giữa annotation và registry, và cách tùy chỉnh dialect phụ thuộc version.

Một ví dụ **minh họa cách kết nối descriptor**, chưa chứa implementation đầy đủ:

~~~java
// InetNetworkJavaType và PostgresInetJdbcType
// là hai class custom ứng dụng cần tự định nghĩa.
@org.hibernate.annotations.JavaType(InetNetworkJavaType.class)
@org.hibernate.annotations.JdbcType(PostgresInetJdbcType.class)
@Column(name = "client_address", columnDefinition = "inet")
private InetNetwork clientAddress;
~~~

Không thể chỉ sao chép đoạn này rồi biên dịch, vì hai lớp descriptor chưa tồn tại. Muốn triển khai SPI ở mức này, cần thực hiện đúng contract interfaces của Hibernate, bao gồm binder/extractor và mutability semantics.

Một custom UserType có thể dễ hiểu hơn cho một thuộc tính đơn giản. SPI theo thành phần thường hợp lý khi cần **tái sử dụng và phối hợp sâu** giữa các kiểu Java, JDBC và dialect.

## 10. Chọn phạm vi áp dụng custom type

Có ba cách tổ chức thường gặp:

1. **Cục bộ theo thuộc tính:** gắn `@Type(PostgresInetUserType.class)` vào field. Dễ xác định nơi phụ thuộc vào Hibernate, nhưng lặp lại nếu có nhiều entity.
2. **Đăng ký dùng chung:** dùng cơ chế type registration/registry của Hibernate để nhiều thuộc tính tự nhận mapping phù hợp. Ít lặp code hơn nhưng cần kiểm soát phạm vi, thứ tự ưu tiên và version.
3. **Descriptor tái sử dụng:** định nghĩa `JavaType`, `JdbcType` dùng chung rồi chọn chúng theo từng mapping/dialect. Phù hợp khi hạ tầng type phức tạp.

Không nên đăng ký một mapping toàn cục nếu cùng kiểu Java đôi khi lưu thành `VARCHAR`, đôi khi lưu bằng PostgreSQL `inet`. Trong tình huống đó, lựa chọn cục bộ hoặc cấu hình rõ ràng theo context giúp tránh áp dụng sai.

Tài liệu Hibernate 5 thường dùng cách đăng ký `UserType` và chữ ký API khác. Khi nâng cấp, không đổi mỗi import rồi cho rằng mapping đã tương đương; phải kiểm tra lại cơ chế registration của Hibernate 6.
## 11. Kiểm tra các mapping tích hợp trước khi tự viết SPI

### 11.1. JSON

Trong những phiên bản Hibernate 6 hỗ trợ, có thể dùng:

~~~java
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import jakarta.persistence.Column;
import java.util.Map;

@JdbcTypeCode(SqlTypes.JSON)
@Column(name = "attributes")
private Map<String, Object> attributes;
~~~

Đây là ví dụ về việc chọn JDBC type mà Hibernate đã hiểu. Ứng dụng cần có cơ chế serialization JSON phù hợp với version và classpath. Database/dialect quyết định kiểu cột, có thể là `jsonb` hoặc kiểu JSON khác. Tự viết UserType chỉ để gọi serializer của riêng ứng dụng có thể là trùng lặp nếu mapping tích hợp đã đủ.

Việc hỗ trợ lưu JSON **không** đồng nghĩa JPQL tự hiểu mọi toán tử JSON đặc thù hay tự tạo index tối ưu. Những yêu cầu truy vấn sâu trong JSON còn liên quan đến SQL dialect và thiết kế schema.

### 11.2. Enum

~~~java
@Enumerated(EnumType.STRING)
@Column(name = "order_status", nullable = false, length = 20)
private OrderStatus status;
~~~

Enum đơn giản thường không cần custom type. Nếu mã lưu trữ ổn định khác với tên enum, một `AttributeConverter<OrderStatus, String>` có thể đủ. Không kết hợp `@Enumerated` với converter theo cách mâu thuẫn trên cùng một thuộc tính.

### 11.3. Các kiểu phổ biến khác

Hibernate/JDBC hỗ trợ nhiều kiểu như `UUID`, Java Time, `byte[]`, `BigDecimal`. Khi gặp các kiểu này, kiểm tra default mapping, annotation có sẵn và dialect trước. Một UserType tự viết cho kiểu đã có hỗ trợ tốt có thể làm ứng dụng khó nâng cấp, thay đổi ngữ nghĩa null, DDL hoặc query parameter mà không có lợi ích rõ rệt.

## 12. Driver, DDL và SQL query là ba trách nhiệm riêng

Xét entity:

~~~java
@Type(PostgresInetUserType.class)
@Column(name = "client_address", columnDefinition = "inet")
private InetNetwork clientAddress;
~~~

và UserType:

~~~java
@Override
public int getSqlType() {
    return Types.OTHER;
}
~~~

Ba tầng cần thống nhất:

| Tầng | Nội dung điều khiển | Kiểm tra ở đâu? |
|---|---|---|
| Mapping Java | Field `InetNetwork` dùng UserType nào | Annotation, registration, Hibernate metadata |
| JDBC | Giá trị được bind/extract bằng cách nào | JDBC driver, UserType/JdbcType, prepared statement |
| Database schema | Cột thực tế có kiểu `inet`, constraint và index nào | Migration, catalog DB, dialect |

Chỉ có `columnDefinition = "inet"` nhưng không có binder phù hợp thì chưa chắc ghi được dữ liệu. Chỉ có binder đúng nhưng schema thực tế vẫn là `VARCHAR` thì mapping cũng có thể sai. Khi dùng migration, thay annotation không tự biến đổi cột trong DB đang chạy.

### SQL extension không tự trở thành JPQL extension

PostgreSQL có các toán tử mạng riêng. Ví dụ một truy vấn SQL:

~~~sql
SELECT id, client_address
FROM login_events
WHERE client_address <<= inet '192.0.2.0/24';
~~~

`<<=` là toán tử liên quan đến mạng của PostgreSQL; ý nghĩa và cú pháp cần được tra cứu theo DB version. UserType giúp ORM ánh xạ kiểu giá trị, **không tự dạy JPQL hiểu mọi toán tử SQL riêng**. Khi cần truy vấn mạng đặc thù, có thể sử dụng HQL extension, đăng ký hàm hoặc native SQL tùy Hibernate version và yêu cầu.

Trong native query, phải chú ý binding của parameter nếu provider không suy luận được UserType từ một entity path. Kiểu cột, kiểu tham số, index và execution plan có thể quyết định hiệu năng truy vấn.

### Vấn đề khả năng chuyển database

Nếu cần hỗ trợ PostgreSQL và MySQL, custom type phụ thuộc `PGobject` không thể tự hoạt động trên mọi JDBC driver. Lựa chọn bao gồm:

- Chuẩn hóa schema ở mức portable, ví dụ lưu ký pháp IP vào chuỗi với validation rõ ràng nếu nghiệp vụ cho phép.
- Định nghĩa một abstraction type ở tầng hạ tầng, ánh xạ khác nhau theo dialect.
- Giới hạn hệ thống ở PostgreSQL và tài liệu hóa phụ thuộc này.
- Sử dụng mapping tích hợp có hỗ trợ đa dialect nếu phù hợp với mục đích.

Cần phân biệt tính di động giữa **provider ORM**, **JDBC driver**, **schema SQL**, và **ngữ nghĩa truy vấn**. Dùng Jakarta Persistence API cho CRUD không đảm bảo mọi custom column và SQL extension portable.

## 13. Sự khác biệt giữa UserType Hibernate 5 và Hibernate 6

Một nguyên nhân gây lỗi khi học custom types là sao chép code từ hướng dẫn không cùng thế hệ Hibernate.

Giao diện trong nhiều ví dụ Hibernate 5 có dạng:

~~~java
// Chỉ minh họa kiểu chữ ký cũ của Hibernate 5,
// không dùng nguyên văn trong Hibernate 6.
int[] sqlTypes();
Object nullSafeGet(ResultSet rs, String[] names, ...);
~~~

Hệ type của Hibernate 6 có các thay đổi đáng kể:

- `UserType<T>` hỗ trợ generic type.
- API mới dùng `getSqlType()` cho một JDBC type code trong UserType cơ bản.
- `nullSafeGet()` dùng vị trí cột `int position` trong `ResultSet`.
- Những trách nhiệm type được tách rõ qua `JavaType`, `JdbcType` và `MutabilityPlan`.
- Annotation `@Type`, cơ chế registration và nhiều API type cũ thay đổi.
- Các hệ Hibernate/JPA mới thường dùng `jakarta.persistence.*` thay cho `javax.persistence.*`.

Việc đổi import có thể chưa đủ. Cần đọc migration guide của Hibernate version đích, xác định mapping sẵn có đã thay thế extension cũ chưa và điều chỉnh code theo contract mới.

**Lưu ý phạm vi:** không phải mọi phiên bản 6.x hay 7.x đều có API, helper, giá trị mặc định và cách đăng ký y hệt. Bài học dùng cơ chế Hibernate 6.x làm nền tảng khái niệm, còn code production phải dựa vào Javadoc/dependency cụ thể.

## 14. Quy trình thiết kế một custom type

Khi phải mở rộng, có thể suy nghĩ theo các bước sau:

1. **Định nghĩa domain value:** giá trị bất biến hay mutable? Cần validation và canonicalization ra sao? Equality biểu diễn gì?
2. **Xác định số cột:** một cột hay nhiều cột? Nếu nhiều cột, xem `@Embeddable` trước.
3. **Xác định biểu diễn lưu trữ:** kiểu cột SQL, JDBC type code và dữ liệu driver thực sự nhận/trả.
4. **Kiểm tra khả năng hiện có:** built-in mapping của Hibernate/dialect, `@JdbcTypeCode`, `@Enumerated`, `AttributeConverter`.
5. **Chọn mức mở rộng:** `UserType` cho một custom basic mapping, hoặc `JavaType/JdbcType` để dùng lại theo thành phần.
6. **Thiết kế read/write/null:** tránh bind type sai; xử lý SQL NULL và representation không hợp lệ.
7. **Thiết kế trạng thái:** equality, hash code, mutability/deep copy, cache representation.
8. **Định nghĩa phạm vi:** cục bộ theo property hay đăng ký dùng chung.
9. **Ràng buộc database:** migration, index, constraints, dialect và SQL query.
10. **Chuẩn bị tương thích phiên bản:** dependency Hibernate, JDBC driver, Jakarta Persistence và migration guide phù hợp.

Đây là quy trình **thiết kế kỹ thuật**. Không nên coi việc viết xong một lớp `UserType` là đã giải quyết toàn bộ các vấn đề về schema, dữ liệu lịch sử, concurrency và vận hành.

## 15. Những lỗi điển hình và ý nghĩa

| Hiện tượng | Nguyên nhân có thể | Điều cần kiểm tra |
|---|---|---|
| Hibernate báo không xác định basic type | Class Java chưa có mapping phù hợp | `@Type`, `@JdbcTypeCode`, converter hoặc registration |
| Cột PostgreSQL `inet` từ chối `VARCHAR` | Converter trả chuỗi nhưng binder dùng JDBC String | Custom JdbcType/UserType hoặc built-in mapping phù hợp |
| SELECT chạy, INSERT lỗi | Đường extract đúng nhưng bind sai JDBC type | `nullSafeSet`, driver, DDL thực |
| INSERT chạy, truy vấn `WHERE` lỗi | Parameter không được suy luận đúng custom type | Typed path, HQL/native binding và Hibernate version |
| Object mutable thay đổi nhưng không có UPDATE | Snapshot/deepCopy/equality không đúng | `isMutable`, `deepCopy`, dirty checking |
| Hibernate luôn UPDATE dù value không đổi | Equality hoặc canonicalization không nhất quán | `equals`, `hashCode`, dữ liệu trả về từ DB |
| Cache trả object bị thay đổi từ nơi khác | Dùng chung reference mutable, disassemble không phù hợp | MutabilityPlan, cache representation |
| Schema tạo ra cột không đúng | JDBC code khác tên DDL/dialect chưa phù hợp | Migration, `columnDefinition`, schema DB |
| Mapping chạy PostgreSQL nhưng lỗi ở H2/MySQL | Phụ thuộc `PGobject` hoặc type `inet` | Chiến lược đa DB và JDBC driver |
| Class `PGobject` không tìm thấy | Thiếu PostgreSQL JDBC dependency | Classpath compile/runtime |
| Ví dụ UserType không compile | Code Hibernate 5 đưa vào Hibernate 6 | Chữ ký `UserType<T>` và Javadoc version |
| Nhiều field mapping trùng một Java type nhưng cần cột khác | Registration toàn cục quá rộng | Mapping cục bộ/descriptor theo context |
| JPQL báo không hiểu toán tử mạng | Toán tử SQL DB không thuộc cú pháp JPQL | Native SQL, HQL extension hoặc function |

Nhìn lỗi cần tách các giai đoạn: metadata Hibernate, chuẩn bị parameter, SQL do ORM sinh, schema thực và ngữ nghĩa của DB. Chỉ dựa vào một annotation thường chưa đủ để kết luận nguyên nhân.

## 16. Bài tập tình huống

### Bài 1 — ProductCode

Bạn có record `ProductCode(String value)` lưu trong `VARCHAR(30)`. Domain cần kiểm tra format và tự chuẩn hóa chữ hoa. Có cần viết UserType?

**Gợi ý:** Converter sang `String` thường đủ, kết hợp validation và DB constraint. Không có yêu cầu JDBC type/binder đặc biệt.

### Bài 2 — Money với hai cột

Một `Money` gồm `amount` và `currency` cần lưu trong `DECIMAL(14,2)` và `VARCHAR(3)`. Chọn UserType một cột hay embeddable?

**Gợi ý:** `@Embeddable` vì mô hình cần hai cột riêng. Có thể dùng `@AttributeOverrides` nếu muốn đổi tên cột theo vị trí nhúng.

### Bài 3 — PostgreSQL inet

DB đã có cột `inet`. Converter trả `String` nhưng lệnh INSERT gặp type mismatch. Thay `@Column(columnDefinition="inet")` có chắc sửa được không?

**Gợi ý:** Không chắc. Cần kiểm tra binder có đang gửi `VARCHAR` hay không. Chọn built-in mapping tương ứng hoặc UserType/JdbcType bind đúng kiểu driver.

### Bài 4 — Mutable value

Custom type quản lý `ByteBuffer` nhưng `deepCopy(value)` trả nguyên reference. Có thể xảy ra điều gì?

**Gợi ý:** Object snapshot và object hiện tại có thể chia sẻ trạng thái thay đổi được; dirty checking/cache không còn đáng tin. Cần xác định khả năng thay đổi và viết copy semantics phù hợp.

### Bài 5 — Đăng ký toàn cục

Cùng class `NetworkValue` được lưu `inet` trong bảng PostgreSQL mới nhưng thành `VARCHAR` ở bảng legacy. Có nên áp một custom UserType cho tất cả field cùng class?

**Gợi ý:** Không nếu hai JDBC mapping khác nhau. Dùng mapping cục bộ hoặc registration được giới hạn đúng phạm vi.

### Bài 6 — Chuyển Hibernate version

Project sử dụng Hibernate 6 nhưng tài liệu code gọi `sqlTypes()` và `nullSafeGet(ResultSet, String[], ...)`. Bạn nên sửa gì trước?

**Gợi ý:** Xác minh nguồn code thuộc Hibernate 5, tra Javadoc/migration guide của phiên bản đích, rồi chuyển contract UserType và cách đăng ký mapping. Đồng thời kiểm tra xem extension cũ còn cần thiết không.

## 17. Ghi nhớ

- `AttributeConverter` chuyển giá trị domain sang một kiểu đích mà provider/JDBC đã hỗ trợ. Nó đơn giản và thuộc Jakarta Persistence.
- `UserType<T>` cho phép custom basic mapping ở mức Hibernate: JDBC type code, đọc ghi, null handling, equality, copy và cache representation.
- `JavaType`, `JdbcType`, `BasicType` và `MutabilityPlan` chia trách nhiệm thành những phần có thể kết hợp, hữu ích cho hạ tầng type phức tạp hoặc tái sử dụng nhiều nơi.
- Mapping một value object vào nhiều cột thường nên bắt đầu bằng `@Embeddable`.
- Hibernate tích hợp nhiều kiểu sẵn có như JSON, enum và UUID; kiểm tra trước khi viết custom extension.
- SQL DDL, JDBC binder/extractor, query semantics và database constraint phải được thiết kế nhất quán.
- Phụ thuộc driver/dialect như PostgreSQL `PGobject` phải được khai báo rõ; code Hibernate 5 và 6 không thể coi là tương thích chỉ nhờ đổi import.

**Mấu chốt:** hãy xác định cụ thể converter đang thiếu điều gì. Nếu chỉ cần chuyển đổi một value object thành `String`, converter đủ. Nếu ứng dụng cần điều khiển **cách Hibernate giao tiếp với JDBC driver** hoặc quản lý tính biến đổi của một giá trị phức tạp, UserType/SPI là công cụ thích hợp hơn.

### Tài liệu chính thức để học sâu

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — converter, basic mapping và embeddable theo chuẩn.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — mapping giá trị cơ bản, type system và custom types.
- [Hibernate ORM 6.6 UserType Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/usertype/UserType.html) — chữ ký giao diện dùng trong ví dụ.
- [Hibernate ORM 6.6 JavaType Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/type/descriptor/java/JavaType.html) — phía Java của hệ type.
- [Hibernate ORM 6.6 JdbcType Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/type/descriptor/jdbc/JdbcType.html) — phía JDBC và các binder/extractor.
- [PostgreSQL Network Address Types](https://www.postgresql.org/docs/current/datatype-net-types.html) — kiểu `inet`, `cidr` và ngữ nghĩa truy vấn mạng.

Tất cả code chứa `PGobject` phụ thuộc PostgreSQL JDBC. Khi áp dụng, hãy dùng chính xác version Hibernate, Jakarta Persistence và driver của project thay vì xem mọi API extension là bất biến qua các bản phát hành.


