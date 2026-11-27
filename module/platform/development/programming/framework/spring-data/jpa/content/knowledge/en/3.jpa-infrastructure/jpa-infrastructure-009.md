# XML Configuration, persistence.xml, and Applicability in Legacy Systems

## 1. Why Do Legacy Systems Often Have XML-Based JPA Configuration?

Older Java applications using JPA commonly declared persistence configuration in a `persistence.xml` file. This approach was widespread in Java EE/Jakarta EE applications running on application servers, Java SE applications bootstrapping JPA manually, or legacy Spring systems that needed to preserve configurations existing for years.

When migrating such an application to Spring Boot and Spring Data JPA, you must understand which part XML describes. JPA configuration typically spans multiple layers of responsibility:

- **Persistence unit metadata:** persistence unit name, provider, transaction type, datasource, and the list of managed classes.
- **Mapping metadata:** how entities, tables, columns, keys, relationships, converters, and listeners are mapped. Metadata may live in annotations or XML files such as `orm.xml`.
- **Provider properties:** settings specific to Hibernate or another JPA provider, such as schema generation behavior, batching, caching, or SQL logging.
- **Spring integration:** how Spring creates `EntityManagerFactory`, manages transactions, injects `EntityManager`, and creates repository proxies.

`persistence.xml` belongs to JPA's metadata layer. It is not a Spring bean configuration file, does not enable component scanning, and does not register Spring Data repository interfaces.

## 2. What Is a Persistence Unit?

A **persistence unit** is a logical group of entities and metadata managed together by a JPA provider. A persistence unit typically specifies:

- A name for the application to reference, such as `legacyUnit`.
- The JPA provider, such as Hibernate.
- The transaction type: `RESOURCE_LOCAL` or `JTA`.
- The datasource or connection details.
- The list of entities and mapping files.
- Configuration properties for the provider.

From a persistence unit, the application creates an `EntityManagerFactory`. Each `EntityManagerFactory` creates `EntityManager` instances; each EntityManager manages a persistence context. Entities are managed within the persistence context attached to that EntityManager.

~~~text
persistence.xml
      |
      v
Persistence Unit: legacyUnit
      |
      v
EntityManagerFactory
      |
      +---- EntityManager A ---- Persistence Context A
      |
      +---- EntityManager B ---- Persistence Context B
~~~

A Java class annotated with `@Entity` does not automatically belong to every persistence unit. It must be included in the metadata of the corresponding persistence unit, via the class list, class discovery rules, or matching Spring/provider configuration. Because of this, a repository can be created successfully yet still fail at runtime if the entity referenced by the repository does not belong to the persistence unit wired to it.

The persistence unit name is not the database name, schema name, or Spring profile name. It is the identifier of the JPA configuration group.

## 3. Location and Structure of persistence.xml

By JPA convention, the configuration file is typically placed at:

~~~text
src/main/resources/
└── META-INF/
    └── persistence.xml
~~~

After building, the file resides on the classpath at `META-INF/persistence.xml`. With Maven or Gradle using the standard resource layout, the `src/main/resources` directory is packaged into the artifact.

The example below illustrates a JPA 3.1 persistence unit using Hibernate and resource-local transactions in a Java SE environment. Driver names, URLs, and connection credentials are illustrative only; never hardcode real passwords in source code or commit them to Git.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="https://jakarta.ee/xml/ns/persistence
                                 https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
             version="3.1">

    <persistence-unit name="legacyUnit"
                      transaction-type="RESOURCE_LOCAL">

        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>

        <class>com.legacy.domain.Customer</class>
        <class>com.legacy.domain.Invoice</class>
        <mapping-file>META-INF/orm.xml</mapping-file>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/legacydb"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="app_user"/>
            <property name="jakarta.persistence.jdbc.password"
                      value="replace-with-secret"/>

            <property name="hibernate.hbm2ddl.auto"
                      value="validate"/>
            <property name="hibernate.show_sql"
                      value="false"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Notable elements:

- `persistence-unit name="legacyUnit"` declares a persistence unit named `legacyUnit`. This name is used when bootstrapping or when Spring selects a persistence unit.
- `transaction-type="RESOURCE_LOCAL"` specifies that transactions are managed via the resource-local mechanism.
- `provider` specifies the JPA implementation, here Hibernate.
- `class` elements list entities included in the persistence unit.
- `mapping-file` declares an additional XML mapping file.
- `exclude-unlisted-classes` controls whether entity classes not explicitly listed are included in the persistence unit. When an exact list is needed, declare the classes explicitly and set the appropriate value.
- `property` elements pass configuration to the JPA provider. Some properties belong to the Jakarta Persistence standard, while others are Hibernate-specific.

The schema and namespace in the example are Jakarta Persistence 3.1. Choose the XML version matching your JPA provider and application platform. Legacy projects using JPA 2.x commonly have the `javax.persistence` namespace and older schemas; you cannot change the namespace alone without upgrading dependencies and source code together.

## 4. Key Configuration Elements

### 4.1. Persistence Unit Name

A single `persistence.xml` file can declare multiple `persistence-unit` elements. Each unit has its own name:

~~~xml
<persistence-unit name="customerUnit">
    ...
</persistence-unit>

<persistence-unit name="reportingUnit">
    ...
</persistence-unit>
~~~

An application can create two EntityManagerFactory instances with different configurations, entity sets, or datasources. This is how a legacy system might separate transactional data from reporting data, or separate modules using different databases.

Do not create multiple persistence units just to split packages. Each unit introduces an additional boundary of entity management, transactions, and connections to operate.

### 4.2. Transaction Type: RESOURCE_LOCAL and JTA

The two transaction types serve different purposes:

| Type | How It Works | Common Context |
|---|---|---|
| `RESOURCE_LOCAL` | Transactions are controlled at the persistence resource level, typically via EntityTransaction or a resource-integrated transaction manager | Java SE applications, Spring applications using one datasource and JpaTransactionManager |
| `JTA` | Transactions are coordinated by a JTA transaction manager, capable of coordinating multiple participating resources | Jakarta EE application servers or systems with distributed transactions |

In Spring applications, `@Transactional` is how transaction boundaries are declared at the business layer. This annotation does not itself decide whether the persistence unit is JTA or resource-local; the configured transaction manager is the actual coordinator.

With resource-local and a single datasource, Spring normally uses `JpaTransactionManager`. With JTA, a JTA transaction manager and appropriate datasource/provider are required. Do not switch `transaction-type` from JTA to RESOURCE_LOCAL just to make the application start if the legacy system relies on distributed transactions.

### 4.3. Datasource: JNDI, JTA, and Non-JTA

In application server environments, datasources are commonly managed outside the application and looked up via JNDI. Example:

~~~xml
<persistence-unit name="legacyUnit" transaction-type="JTA">
    <jta-data-source>java:comp/env/jdbc/LegacyDS</jta-data-source>
</persistence-unit>
~~~

`jta-data-source` references a datasource participating in JTA transactions. For a datasource not participating in JTA, metadata can use `non-jta-data-source`.

In Spring Boot applications that manage their own datasource, the datasource is typically configured with `spring.datasource.*` and created as a Spring bean. When integrating an XML persistence unit into Spring, choose a clear datasource source: use the Spring-supplied datasource or the deployment environment's JNDI datasource. Avoid configuring two conflicting connection sources in the same persistence unit.

### 4.4. Class List and exclude-unlisted-classes

There are two common ways to identify entities in a persistence unit:

- List classes via `class` elements.
- Allow the provider to discover entity classes within the archive/persistence unit scope per JPA rules.

Explicit listing example:

~~~xml
<class>com.legacy.customer.Customer</class>
<class>com.legacy.order.Order</class>
<exclude-unlisted-classes>true</exclude-unlisted-classes>
~~~

Explicit listing is useful when a legacy system has multiple modules or needs strict control over which entities belong to each persistence unit. However, whenever a new entity is added, the corresponding list must be updated if unlisted classes are excluded.

`exclude-unlisted-classes` is not a Spring package scanning annotation. It controls class discovery inside the persistence unit per JPA metadata.

## 5. Distinguishing persistence.xml, orm.xml, and hibernate.cfg.xml

Three XML files are frequently confused but serve different roles:

| File | Purpose |
|---|---|
| `META-INF/persistence.xml` | Declares persistence units, provider, transaction type, datasource, class list, and JPA/provider properties |
| `META-INF/orm.xml` | Declares or supplements entity mappings per JPA's standard ORM XML |
| `hibernate.cfg.xml` | Hibernate-specific bootstrap configuration file in traditional Hibernate integration |

### 5.1. orm.xml Used for Entity Mapping

`orm.xml` can be used when a system wants to keep mappings outside Java code, when mappings vary by module, or when maintaining XML metadata during a migration phase.

Abbreviated example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings xmlns="https://jakarta.ee/xml/ns/persistence/orm"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xsi:schemaLocation="https://jakarta.ee/xml/ns/persistence/orm
                                     https://jakarta.ee/xml/ns/persistence/orm_3_1.xsd"
                 version="3.1">

    <entity class="com.legacy.domain.Customer" access="FIELD">
        <table name="customers"/>
        <attributes>
            <id name="id">
                <generated-value strategy="IDENTITY"/>
            </id>
            <basic name="name">
                <column name="customer_name" nullable="false"/>
            </basic>
        </attributes>
    </entity>
</entity-mappings>
~~~

This file describes the mapping for `Customer`: table `customers`, primary key `id`, and column `customer_name` for attribute `name`. Ensure attribute names in XML match the Java class structure and mappings do not conflict with other metadata.

ORM XML is mapping metadata. It does not replace a persistence unit and does not create Spring beans.

### 5.2. hibernate.cfg.xml Is Not Synonymous with persistence.xml

`hibernate.cfg.xml` belongs to Hibernate's proprietary bootstrapping and configuration approach. A legacy Hibernate system may use it to declare datasources, mapping resources, and Hibernate properties. When migrating to standard JPA or Spring Data JPA, determine which bootstrap API reads the configuration.

Do not copy the contents of `hibernate.cfg.xml` verbatim into `persistence.xml` without cross-checking property names and meanings. Some Hibernate settings can become provider properties, while others belong to the environment's datasource or transaction manager.

## 6. How Does Spring Data JPA Use persistence.xml?

Spring Data JPA does not read `persistence.xml` directly to create repositories. The typical chain of responsibility is:

1. Spring creates or obtains an `EntityManagerFactory`.
2. EntityManagerFactory is bootstrapped from the persistence unit and provider.
3. Spring Data JPA creates repository proxies and wires repositories to the corresponding EntityManagerFactory.
4. Services call repositories; the transaction manager manages transaction boundaries.

In modern Spring Boot applications, the standard approach is letting Boot create EntityManagerFactory from the datasource, entity packages, and settings in `application.properties` or `application.yml`. When using this approach, there is usually no need to write `persistence.xml`.

A legacy system may need to keep XML persistence units because it relies on JNDI, JTA, XML mappings, or multiple persistence units. In that case, integrate the persistence unit explicitly with Spring.

### 6.1. Integrating an XML Persistence Unit into Spring

Spring Framework provides `LocalContainerEntityManagerFactoryBean` to create an EntityManagerFactory from persistence unit metadata. The example below illustrates a resource-local persistence unit using a Spring-supplied datasource:

~~~java
package com.legacy.config;

import jakarta.persistence.EntityManagerFactory;
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.orm.jpa.JpaVendorAdapter;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.legacy.customer.repository",
    entityManagerFactoryRef = "legacyEntityManagerFactory",
    transactionManagerRef = "legacyTransactionManager"
)
public class LegacyJpaConfiguration {

    @Bean
    public JpaVendorAdapter jpaVendorAdapter() {
        return new HibernateJpaVendorAdapter();
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean legacyEntityManagerFactory(
            DataSource dataSource,
            JpaVendorAdapter jpaVendorAdapter) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();

        factory.setPersistenceXmlLocation(
                "classpath:META-INF/persistence.xml");
        factory.setPersistenceUnitName("legacyUnit");
        factory.setDataSource(dataSource);
        factory.setJpaVendorAdapter(jpaVendorAdapter);

        return factory;
    }

    @Bean
    public PlatformTransactionManager legacyTransactionManager(
            EntityManagerFactory legacyEntityManagerFactory) {
        return new JpaTransactionManager(legacyEntityManagerFactory);
    }
}
~~~

Meaning:

- `setPersistenceXmlLocation` specifies the XML file location on the classpath.
- `setPersistenceUnitName` selects the exact unit declared in XML.
- `setDataSource` supplies the Spring-managed datasource to the persistence unit in this integration style.
- `JpaVendorAdapter` provides integration between Spring ORM and the provider, here Hibernate.
- `@EnableJpaRepositories` specifies the repository package and wires them to the right EntityManagerFactory and transaction manager.
- `JpaTransactionManager` coordinates resource-local JPA transactions for the passed EntityManagerFactory.

The example uses `jakarta.persistence` imports for Spring Boot 3+ and compatible Spring Framework versions. In Spring Boot 2/JPA 2.x projects, JPA imports typically use `javax.persistence`. Do not mix the two API generations.

If using a Spring-managed datasource, choose one unified connection configuration source. In this example, the datasource is passed via `setDataSource`; avoid simultaneously maintaining different URLs/drivers/passwords in XML such that operators cannot tell which configuration is active.

This is an explicit integration configuration for legacy scenarios. Before applying it, check the Spring Framework version, JPA provider, transaction type, and how datasources are managed in the real environment. With JTA, configure a JTA transaction manager and appropriate datasource/provider instead of using `JpaTransactionManager` as in the resource-local example.

### 6.2. Selecting EntityManager by Persistence Unit

If the application has multiple EntityManagerFactory instances, you can specify the persistence unit when injecting EntityManager:

~~~java
@PersistenceContext(unitName = "legacyUnit")
private EntityManager entityManager;
~~~

The name `legacyUnit` must match the configured persistence unit. Omitting the name in an application with multiple units can make EntityManager selection ambiguous or bind it to the wrong persistence unit.

For Spring Data repositories, the `entityManagerFactoryRef` and `transactionManagerRef` attributes in `@EnableJpaRepositories` serve a similar role: they specify the infrastructure that the repository group will use.

## 7. Scope of Applicability in Legacy Systems

### 7.1. Persistence Unit Defines Entity Scope

A persistence unit manages its set of entities and mappings. If an entity does not belong to the unit, that unit's EntityManagerFactory cannot manage the entity as expected.

For example, if `legacyUnit` only contains:

~~~xml
<class>com.legacy.customer.Customer</class>
<class>com.legacy.customer.Address</class>
~~~

then you cannot assume `com.legacy.audit.AuditEvent` is also managed in the same unit. It must be added to the metadata or entity discovery must be configured intentionally.

This is JPA's management scope, distinct from Spring's component scan scope.

### 7.2. Repository Package Defines the Registered Interface Group

Repository scanning determines which interfaces Spring Data creates proxies for. It does not automatically add entities to a persistence unit.

With multiple persistence units, split repository packages by module or by datasource and declare explicitly:

~~~java
@EnableJpaRepositories(
    basePackages = "com.legacy.customer.repository",
    entityManagerFactoryRef = "customerEntityManagerFactory",
    transactionManagerRef = "customerTransactionManager"
)
~~~

This repository group will use the specified EntityManagerFactory and transaction manager. Pointing a repository group to the wrong factory can cause unmanaged entity errors or queries hitting the wrong database.

### 7.3. An Application Can Have Multiple Persistence Units

Example of a system with a transactional database and a reporting database:

~~~text
Spring Application
  |
  +-- customer repositories
  |       |
  |       +-- customerEntityManagerFactory
  |               |
  |               +-- customerUnit
  |                       |
  |                       +-- customerDataSource
  |
  +-- reporting repositories
          |
          +-- reportingEntityManagerFactory
                  |
                  +-- reportingUnit
                          |
                          +-- reportingDataSource
~~~

Each group must explicitly configure:

- The persistence unit and corresponding entity set.
- EntityManagerFactory.
- Datasource or JNDI datasource.
- Transaction manager.
- Repository package bound to that factory.

If an atomic transaction spanning multiple databases/resources is required, you cannot assume two separate JpaTransactionManager instances will coordinate into a distributed transaction. JTA or another consistency design matching business requirements is needed.

## 8. When to Keep XML vs. Move to Modern Configuration?

Not every system needs to delete `persistence.xml`. The decision depends on what XML currently controls.

**Consider keeping XML when:**

- The application runs in an application server and uses JNDI/JTA.
- There are multiple persistence units with separate entity sets and datasources.
- XML mappings hold numerous rules, overrides, or metadata that should not be altered during an upgrade phase.
- Multiple legacy modules rely on existing persistence unit names or bootstrapping mechanisms.
- Minimizing change scope is needed when upgrading a stable running system.

**You can gradually move to Spring Boot configuration when:**

- The application has only a single datasource and a simple single persistence unit.
- Entities are already managed via annotations and do not require special XML mappings.
- There is no reliance on application server JNDI/JTA.
- You want centralized management of connection and provider settings via Spring configuration.
- The team can thoroughly test behavior before and after the transition.

Boot configuration typically places connectivity in `spring.datasource.*` and JPA options in `spring.jpa.*`. Declaring entity packages can rely on the root package or entity scan configuration. Repositories can be auto-configured according to the default package layout or declared explicitly when multiple groups exist.

Do not convert all XML to annotations solely to use Spring Boot. If XML contains mappings with business significance or environment transaction settings, keep it until tests prove that changing it does not alter behavior.

## 9. Process for Migrating a Legacy System

A cautious roadmap may include the following steps:

1. **Inventory persistence units:** record unit names, providers, transaction types, datasource/JNDI names, class lists, mapping files, and provider properties.
2. **Inventory mappings:** identify whether mappings reside in annotations, `orm.xml`, Hibernate mapping XML, or convention. Record generators, converters, listeners, named queries, relationships, and fetch strategies.
3. **Identify transaction environment:** whether the app uses resource-local, JTA, or a framework/application server-specific transaction manager. Clearly determine who begins, commits, and rolls back transactions.
4. **Keep schema stable:** use a schema validation mode such as `validate` during verification. Do not enable automatic schema creation/dropping on databases holding production data.
5. **Upgrade APIs together:** when migrating from Spring Boot 2/JPA 2.x to Spring Boot 3+/Jakarta Persistence, update the `javax.persistence` namespace to `jakarta.persistence` together with compatible providers and dependencies.
6. **Migrate one persistence unit at a time:** if there are multiple units, migrate and test one group at a time, preserving accurate datasource and repository mappings.
7. **Test transactions and queries:** test commit/rollback, lazy loading, relationships, auto-generated keys, named queries, native queries, optimistic locking, and repository operations.
8. **Compare SQL and data:** compare generated SQL, query results, and schema before/after. Use SQL logs in test environments when needed.
9. **Controlled rollout:** monitor bootstrap, connection, transaction, and query errors after upgrading; prepare an appropriate rollback plan.

If the schema must change, use a migration management tool such as Flyway or Liquibase to version changes. Migrating JPA configuration should not simultaneously make unrelated schema changes without separate testing.

## 10. Common Errors and Troubleshooting

### 10.1. Persistence Unit Not Found

Errors typically occur when the provider or Spring cannot locate the unit with the requested name.

Check:

- Is the file packaged at `META-INF/persistence.xml`?
- Does the name in `setPersistenceUnitName` or `@PersistenceContext(unitName=...)` match exactly?
- Is the file placed on the classpath of the module bootstrapping JPA?
- Does the XML have the right namespace and schema version for the provider?

### 10.2. Entity Not Managed

Messages such as `Not a managed type` usually mean the entity does not belong to the persistence unit in use.

Check:

- Does the class have `@Entity` or appropriate XML mapping?
- Is the class listed in the unit?
- Does `exclude-unlisted-classes` exclude that class?
- Is the repository wired to the wrong EntityManagerFactory?
- Is the entity registered in a different persistence unit rather than the one used by the repository?

Do not try to solve this error by merely widening component scanning; that is a different mechanism.

### 10.3. Datasource or JNDI Does Not Exist

If the application reports datasource not found, check the JNDI name, resource configuration on the application server, permissions, driver, and deployment environment. Datasource names on developer machines may differ from staging or production environments.

If using Spring Boot to manage the datasource, check `spring.datasource.*` settings and the DataSource bean passed to EntityManagerFactory. Avoid pointing to JNDI while also passing a different datasource unintentionally.

### 10.4. Transactions Not Managed Properly

Symptoms can include data not rolling back as expected, errors stating no active transaction exists, or multiple operations across datasources not sharing a transaction.

Check the transaction type in the persistence unit, Spring transaction manager, how datasources participate in JTA, and where `@Transactional` is placed. With multiple persistence units, explicitly determine which transaction manager governs each service/repository.

### 10.5. Mixing Up javax and jakarta Namespaces

Spring Boot 3+ moved to the Jakarta EE namespace. If entities use `jakarta.persistence.Entity` while an old provider or library only supports `javax.persistence.Entity`, classes may not be recognized properly.

Inspect the dependency tree and versions of Spring Boot, Spring Data JPA, Hibernate, JPA API, and shared modules. Upgrade them together rather than changing imports in only a few classes.

### 10.6. Configuration Declared in Multiple Places

A system might declare datasources in XML, application properties, environment variables, and application server configuration simultaneously. When that happens, the active value may differ from what operators think is being used.

Establish one authoritative configuration source per environment, manage secrets outside source code, and document intentional overrides. Never commit connection passwords or tokens to Git.

## 11. Takeaways

- `persistence.xml` declares persistence units and JPA bootstrap metadata.
- A persistence unit defines the set of entities, mappings, provider, transaction type, and datasource managed together.
- `orm.xml` describes entity mappings in XML; `hibernate.cfg.xml` belongs to Hibernate's proprietary configuration mechanism.
- Spring Data JPA requires a Spring-managed or provided EntityManagerFactory; it creates repository proxies based on that factory.
- Component scan, entity membership, and repository scan are distinct scopes.
- Legacy systems can retain XML if XML expresses required transaction boundaries, datasources, or mappings.
- When migrating to Spring Boot/Jakarta, upgrade APIs, providers, datasources, and transactions together, then test behavior before modifying live environments.

Understanding the exact scope of a persistence unit prevents confusion between discovering a class, JPA managing that entity, and Spring Data generating a repository for the entity. This is critical when maintaining long-lived Spring Data JPA applications or integrating multiple data modules.